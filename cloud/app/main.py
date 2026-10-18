"""Cloud service: CloudService (composition layer) + the FastAPI app.

    Zenoh sample -> on_telemetry / on_hazard -> FleetAnalytics -> events
                 -> handle(events): Store saves them, broadcaster pushes them
                    to every dashboard over the WebSocket

Run the cloud on its own (next phase):
    python -m cloud.app.main

NEXT PHASE: nothing here should change. Set TRANSPORT=zenoh and
DATABASE_URL=postgresql://... (see transport.py and store.py).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analytics import FleetAnalytics, latency_stats
from .config import CloudConfig
from .store import Store
from .transport import HAZARD_KEYS, TELEMETRY_KEYS, open_session

STATIC_DIR = Path(__file__).resolve().parent / "static"


class CloudService:
    def __init__(self, cfg: CloudConfig, session: Any, store: Store, analytics: FleetAnalytics) -> None:
        self.cfg = cfg
        self.session = session
        self.store = store
        self.analytics = analytics
        self.lock = threading.Lock()          # FleetAnalytics is not thread-safe on its own
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue | None = None
        self._subs: list[Any] = []
        self._stop = threading.Event()

    # ------------------------------------------------------------- lifecycle
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue = asyncio.Queue()
        self._subs.append(self.session.declare_subscriber(TELEMETRY_KEYS, self.on_telemetry))
        self._subs.append(self.session.declare_subscriber(HAZARD_KEYS, self.on_hazard))
        threading.Thread(target=self.offline_checker, name="offline-checker", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for sub in self._subs:
            sub.undeclare()

    # ---------------------------------------------- inputs (Zenoh threads)
    def on_telemetry(self, sample: Any) -> None:
        msg = _decode(sample)
        if msg is not None:
            with self.lock:
                self.handle(self.analytics.ingest_telemetry(msg, time.time()))

    def on_hazard(self, sample: Any) -> None:
        msg = _decode(sample)
        if msg is not None:
            with self.lock:
                self.handle(self.analytics.ingest_hazard(msg, time.time()))

    def offline_checker(self) -> None:
        while not self._stop.wait(2.0):
            with self.lock:
                self.handle(self.analytics.check_offline(time.time()))

    # ------------------------------------------------- persist + broadcast
    def handle(self, events: list[dict]) -> None:
        for ev in events:
            kind = ev["kind"]
            if kind == "telemetry":
                self.store.add_telemetry(ev["data"])
            elif kind == "alert":
                alert = ev["data"]
                if alert["source"] == "edge":  # a new hazard replaces the old one of the same type
                    self.store.clear_alerts(alert["vehicle_id"], alert["ts_ms"], "edge", alert["type"])
                alert["id"] = self.store.add_alert(alert)
                alert["status"] = "active"
                self.push({"kind": "alert", "data": alert})
            elif kind == "clear":
                if self.store.clear_alerts(ev["vehicle_id"], int(time.time() * 1000), ev["source"], ev["type"]):
                    self.push({"kind": "alerts_changed"})
            elif kind == "trip":
                self.store.add_trip(ev["data"])
                self.push(ev)
            elif kind == "twin":
                self.push(ev)

    def push(self, event: dict) -> None:
        """Thread-safe: hand the event to the asyncio loop for broadcasting."""
        if self.loop is not None and self.queue is not None and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    async def broadcaster(self) -> None:
        assert self.queue is not None
        while True:
            event = await self.queue.get()
            dead = []
            for ws in list(self.clients):
                try:
                    await ws.send_json(event)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)


def _decode(sample: Any) -> dict | None:
    try:
        return json.loads(sample.payload.to_string())
    except (ValueError, AttributeError):
        return None


def load_fleet(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def create_app(cfg: CloudConfig | None = None, session: Any = None) -> FastAPI:
    cfg = cfg or CloudConfig.from_env()
    fleet = load_fleet(cfg.fleet_config)
    service = CloudService(
        cfg,
        session or open_session(cfg.transport, cfg.zenoh_endpoint),
        Store(cfg.database_url),
        FleetAnalytics(fleet, cfg.offline_after_s),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service.start(asyncio.get_running_loop())
        task = asyncio.create_task(service.broadcaster())
        yield
        service.stop()
        task.cancel()

    app = FastAPI(title="SDV Fleet Monitor", lifespan=lifespan)
    app.state.service = service
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "transport": cfg.transport, "database": cfg.database_url.split(":")[0],
                "vehicles": len(service.analytics.twins)}

    @app.get("/api/fleet")
    def fleet_view() -> list[dict]:
        with service.lock:
            return service.analytics.snapshot()

    @app.get("/api/alerts")
    def alerts(limit: int = 50) -> dict:
        return {"active": service.store.active_alert_count(), "items": service.store.recent_alerts(limit)}

    @app.post("/api/alerts/{alert_id}/ack")
    def ack(alert_id: int) -> dict:
        if service.store.get_alert(alert_id) is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        service.store.ack_alert(alert_id)
        service.push({"kind": "alerts_changed"})
        return {"ok": True, "id": alert_id}

    @app.get("/api/latency")
    def latency() -> dict:
        return latency_stats(service.store.latencies())

    @app.get("/api/routes")
    def routes() -> list[dict]:
        names = service.analytics.routes
        rows = {r["route_id"]: r for r in service.store.route_summary()}
        out = []
        for route_id in sorted(set(names) | set(rows)):
            r = rows.get(route_id, {"trips": 0, "distance_km": 0, "trip_hazards": 0,
                                    "avg_energy_pct": None, "hazard_alerts": 0})
            km = r["distance_km"] or 0
            out.append({
                "route_id": route_id,
                "name": names.get(route_id, {}).get("name", route_id),
                "trips": r["trips"],
                "distance_km": round(km, 1),
                "hazards_per_100km": round(r["trip_hazards"] * 100 / km, 1) if km > 0 else None,
                "avg_energy_pct": round(r["avg_energy_pct"], 2) if r["avg_energy_pct"] is not None else None,
                "hazard_alerts": r["hazard_alerts"],
            })
        return out

    @app.get("/api/trips")
    def trips(limit: int = 20) -> list[dict]:
        return service.store.recent_trips(limit)

    @app.get("/api/history/{vehicle_id}")
    def history(vehicle_id: str, minutes: float = 10) -> list[dict]:
        return service.store.history(vehicle_id, int((time.time() - minutes * 60) * 1000))

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        service.clients.add(websocket)
        with service.lock:
            snapshot = service.analytics.snapshot()
        await websocket.send_json({"kind": "snapshot", "fleet": snapshot, "transport": cfg.transport})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            service.clients.discard(websocket)

    return app


def main() -> None:
    import uvicorn
    cfg = CloudConfig.from_env()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()
