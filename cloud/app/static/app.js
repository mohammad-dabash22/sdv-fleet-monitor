// SDV Fleet Monitor dashboard (plain JavaScript, no build step).
//
// Data comes from the cloud service only:
//   WebSocket /ws          live events: snapshot, twin, alert, alerts_changed, trip
//   GET /api/alerts        alert queue          POST /api/alerts/{id}/ack
//   GET /api/latency       latency stats        GET /api/routes   route table
//
// NEXT PHASE: nothing here depends on mock data. Phase 2 adds fleet history
// (GET /api/history/{vehicle_id}) and more route columns.

"use strict";

const ROUTE_COLORS = { A: "#2563eb", B: "#d97706", C: "#059669" };
const SEVERITY = { 1: "Warning", 2: "High", 3: "Critical" };
const SEV_COLORS = { 1: "#b98900", 2: "#e2620e", 3: "#d42a2a" };
const TYPE_LABELS = {
  HARSH_BRAKING: "Harsh braking",
  TRACTION_LOSS: "Traction loss",
  OVERSPEED: "Overspeed",
  LOW_ENERGY: "Low battery",
  OVERHEAT: "Overheating",
  OFFLINE: "Vehicle offline",
  ENERGY_DROP: "Sudden battery drop",
};
const TRAIL_POINTS = 40;
const MAX_HAZARD_MARKERS = 250;

const state = {
  fleet: new Map(),     // vehicle_id -> twin
  markers: new Map(),   // vehicle_id -> Leaflet marker
  trails: new Map(),    // vehicle_id -> Leaflet polyline
  hazardMarkers: [],
  alerts: [],
  shownAlertIds: new Set(),
  map: null,
  hazardLayer: null,
};

const $ = (id) => document.getElementById(id);
const routeColor = (r) => ROUTE_COLORS[r] || "#6b7280";
const typeLabel = (t) => TYPE_LABELS[t] || t;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v, d = 0) => (v === null || v === undefined ? "-" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const shortName = (twin) => (twin.name || twin.vehicle_id).replace(/^\D+/, "");

function timeAgo(ms) {
  if (!ms) return "";
  const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

// ------------------------------------------------------------------ map
function initMap() {
  if (!window.L) {
    $("map").innerHTML = '<p class="empty">Map library did not load.</p>';
    return;
  }
  state.map = L.map("map", { zoomControl: true }).setView([43.915, -78.868], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
  state.hazardLayer = L.layerGroup().addTo(state.map);
}

function renderLegend() {
  const routes = [...new Set([...state.fleet.values()].map((t) => t.route_id))].sort();
  $("legend").innerHTML =
    routes.map((r) => `<span><i style="background:${routeColor(r)}"></i>Route ${esc(r)}</span>`).join("") +
    `<span class="muted">Hazards:</span>` +
    [1, 2, 3].map((s) => `<span><i style="background:${SEV_COLORS[s]};opacity:.7"></i>${SEVERITY[s]}</span>`).join("");
}

function updateVanOnMap(twin) {
  const t = twin.telemetry || {};
  if (!state.map || t.lat == null || t.lon == null) return;
  const pos = [t.lat, t.lon];
  const cls = ["van-icon", twin.online ? "" : "offline", twin.hazard ? "hazard" : ""].join(" ");
  const icon = L.divIcon({
    className: "",
    html: `<div class="${cls}" style="--c:${routeColor(twin.route_id)}">${esc(shortName(twin))}</div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
  let marker = state.markers.get(twin.vehicle_id);
  if (!marker) {
    marker = L.marker(pos, { icon, zIndexOffset: 1000 }).addTo(state.map);
    state.markers.set(twin.vehicle_id, marker);
  } else {
    marker.setLatLng(pos);
    marker.setIcon(icon);
  }
  marker.bindTooltip(`${esc(twin.name)} · Route ${esc(twin.route_id)} · ${num(t.speed_kmh)} km/h`);

  let trail = state.trails.get(twin.vehicle_id);
  if (!trail) {
    trail = L.polyline([], { color: routeColor(twin.route_id), weight: 4, opacity: 0.45 }).addTo(state.map);
    state.trails.set(twin.vehicle_id, trail);
  }
  const pts = trail.getLatLngs();
  pts.push(pos);
  if (pts.length > TRAIL_POINTS) pts.shift();
  trail.setLatLngs(pts);
}

function addHazardMarker(a) {
  if (!state.hazardLayer || a.lat == null || a.lon == null || a.source !== "edge") return;
  const m = L.circleMarker([a.lat, a.lon], {
    radius: 4 + (a.severity || 1),
    color: SEV_COLORS[a.severity] || SEV_COLORS[1],
    weight: 1,
    fillOpacity: 0.55,
  }).bindPopup(`<b>${esc(typeLabel(a.type))}</b><br>${esc(a.vehicle_name)} · Route ${esc(a.route_id)}<br>${esc(a.detail)}`);
  m.addTo(state.hazardLayer);
  state.hazardMarkers.push(m);
  if (state.hazardMarkers.length > MAX_HAZARD_MARKERS) state.hazardLayer.removeLayer(state.hazardMarkers.shift());
}

// ---------------------------------------------------------------- fleet
let fleetFrame = 0;
function renderFleetSoon() {
  if (!fleetFrame) fleetFrame = requestAnimationFrame(() => { fleetFrame = 0; renderFleet(); });
}

function renderFleet() {
  const twins = [...state.fleet.values()].sort((a, b) => a.vehicle_id.localeCompare(b.vehicle_id));
  $("online-count").textContent = `${twins.filter((t) => t.online).length}/${twins.length}`;
  $("fleet").innerHTML = twins.map((tw) => {
    const t = tw.telemetry || {};
    const soc = t.soc_pct;
    const chip = tw.hazard
      ? `<span class="chip hz">${esc(typeLabel(tw.hazard.type))}</span>`
      : tw.online ? '<span class="chip">Online</span>' : '<span class="chip off">Offline</span>';
    return `
      <div class="van ${tw.hazard ? "hazard" : ""} ${tw.online ? "" : "offline"}" style="--c:${routeColor(tw.route_id)}">
        <div class="van-head"><b>${esc(tw.name)}</b><span class="muted">Route ${esc(tw.route_id)}</span>${chip}</div>
        <div class="van-stats">
          <div><label>Speed</label><b>${num(t.speed_kmh)}</b><label>km/h</label></div>
          <div><label>Battery</label><b>${num(soc)}%</b>
            <div class="bar"><i class="${soc < 25 ? "low" : ""}" style="width:${Math.max(0, Math.min(100, soc || 0))}%"></i></div></div>
          <div><label>Trip</label><b>#${esc(t.trip_id ?? "-")}</b></div>
          <div><label>Odometer</label><b>${num(t.odometer_km)}</b><label>km</label></div>
        </div>
        ${tw.hazard ? `<div class="van-hazard">${esc(tw.hazard.detail)}</div>` : ""}
      </div>`;
  }).join("");
}

function upsertTwin(twin) {
  state.fleet.set(twin.vehicle_id, twin);
  updateVanOnMap(twin);
  renderFleetSoon();
}

// --------------------------------------------------------------- alerts
function renderAlerts() {
  const showResolved = $("show-resolved").checked;
  const items = state.alerts.filter((a) => showResolved || a.status === "active");
  if (!items.length) {
    $("alerts").innerHTML = `<li class="empty">${showResolved ? "No alerts yet." : "No active alerts."}</li>`;
    return;
  }
  $("alerts").innerHTML = items.map((a) => {
    const meta = [timeAgo(a.ts_ms), a.latency_ms != null ? `latency ${num(a.latency_ms)} ms` : null,
      a.source === "cloud" ? "cloud rule" : "detected on vehicle"].filter(Boolean).join(" · ");
    const action = a.status === "active"
      ? `<button data-ack="${a.id}">Acknowledge</button>`
      : `<span class="status">${a.status === "acked" ? "Acknowledged" : "Resolved"}</span>`;
    return `
      <li class="alert sev${a.severity} ${a.status === "active" ? "" : "done"}">
        <div class="alert-body">
          <div class="alert-title"><span class="sev-tag">${esc(SEVERITY[a.severity] || "Info")}</span>
            <b>${esc(typeLabel(a.type))}</b><span class="muted">${esc(a.vehicle_name)} · Route ${esc(a.route_id)}</span></div>
          <div class="alert-detail">${esc(a.detail)}</div>
          <div class="alert-meta">${esc(meta)}</div>
        </div>
        ${action}
      </li>`;
  }).join("");
}

async function ack(id) {
  await fetch(`/api/alerts/${id}/ack`, { method: "POST" });
  refreshSoon();
}

let toastTimer = 0;
function toast(a) {
  if ((a.severity || 0) < 2) return;
  const el = $("toast");
  el.style.borderLeftColor = SEV_COLORS[a.severity];
  el.innerHTML = `<b>${esc(SEVERITY[a.severity])}: ${esc(typeLabel(a.type))}</b><br>${esc(a.vehicle_name)} · Route ${esc(a.route_id)}<br><span style="opacity:.8">${esc(a.detail)}</span>`;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 5000);
}

// ------------------------------------------------------ latency + routes
function renderLatency(s) {
  $("lat-count").textContent = s.count;
  $("lat-median").textContent = s.median_ms == null ? "-" : `${num(s.median_ms)} ms`;
  $("lat-p95").textContent = s.p95_ms == null ? "-" : `${num(s.p95_ms)} ms`;
  $("lat-max").textContent = s.max_ms == null ? "-" : `${num(s.max_ms)} ms`;
  const v = $("latency-verdict");
  if (s.pass == null) { v.className = "verdict"; v.textContent = "No data yet"; return; }
  v.className = `verdict ${s.pass ? "pass" : "fail"}`;
  v.textContent = `${s.pass ? "Pass" : "Fail"}: p95 ${s.pass ? "<" : ">="} ${num(s.target_ms)} ms`;
}

function renderRoutes(rows) {
  const worst = rows.reduce((w, r) => (r.hazards_per_100km != null && (!w || r.hazards_per_100km > w.hazards_per_100km) ? r : w), null);
  $("routes").innerHTML = rows.map((r) => `
    <tr class="${worst && r.route_id === worst.route_id && rows.length > 1 ? "worst" : ""}">
      <td style="--c:${routeColor(r.route_id)}"><span class="dot"></span>${esc(r.name)}</td>
      <td>${r.trips}</td>
      <td>${num(r.distance_km, 1)} km</td>
      <td><b>${r.hazards_per_100km == null ? "-" : num(r.hazards_per_100km, 1)}</b></td>
      <td>${r.avg_energy_pct == null ? "-" : `${num(r.avg_energy_pct, 2)}%`}</td>
      <td>${r.hazard_alerts}</td>
    </tr>`).join("");
}

// ------------------------------------------------------------- refresh
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

async function refreshAll() {
  try {
    const [alerts, latency, routes] = await Promise.all([
      getJSON("/api/alerts?limit=100"), getJSON("/api/latency"), getJSON("/api/routes"),
    ]);
    state.alerts = alerts.items;
    $("active-count").textContent = alerts.active;
    for (const a of alerts.items) {
      if (!state.shownAlertIds.has(a.id)) { state.shownAlertIds.add(a.id); addHazardMarker(a); }
    }
    renderAlerts();
    renderLatency(latency);
    renderRoutes(routes);
  } catch (err) {
    console.warn("refresh failed", err);
  }
}

let refreshTimer = 0;
function refreshSoon() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refreshAll, 250);
}

// ------------------------------------------------------------ websocket
function setConnection(live) {
  const el = $("conn");
  el.className = `pill conn ${live ? "live" : "down"}`;
  el.querySelector("span").textContent = live ? "Live" : "Reconnecting";
}

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => setConnection(true);
  ws.onclose = () => { setConnection(false); setTimeout(connect, 2000); };
  ws.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    switch (ev.kind) {
      case "snapshot":
        $("mock-badge").hidden = ev.transport !== "fake";
        ev.fleet.forEach(upsertTwin);
        renderLegend();
        refreshAll();
        break;
      case "twin":
        upsertTwin(ev.data);
        break;
      case "alert":
        state.shownAlertIds.add(ev.data.id);
        addHazardMarker(ev.data);
        if (ev.data.source === "edge" || ev.data.severity >= 2) toast(ev.data);
        refreshSoon();
        break;
      case "alerts_changed":
      case "trip":
        refreshSoon();
        break;
    }
  };
}

// ----------------------------------------------------------------- start
document.addEventListener("click", (e) => {
  const id = e.target?.dataset?.ack;
  if (id) ack(id);
});
$("show-resolved").addEventListener("change", renderAlerts);
setInterval(renderAlerts, 5000);   // keep "12s ago" fresh
setInterval(refreshAll, 15000);    // safety net if an event is missed
initMap();
connect();
