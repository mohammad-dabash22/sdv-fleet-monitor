"""Deployment rules checked against parsed manifest documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .images import resolves_to_latest

PLACEHOLDER = "IMAGE_PLACEHOLDER"
RWO_MODES = {"ReadWriteOnce", "ReadWriteOncePod"}

# Where each workload kind keeps its pod spec.
POD_SPEC_PATHS = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


@dataclass(frozen=True)
class Document:
    source: str
    body: Dict[str, Any]

    @property
    def kind(self) -> str:
        return str(self.body.get("kind") or "<unknown>")

    @property
    def name(self) -> str:
        return str(_get(self.body, "metadata", "name") or "<unnamed>")

    @property
    def namespace(self) -> Optional[str]:
        return _get(self.body, "metadata", "namespace")


@dataclass(frozen=True)
class Finding:
    source: str
    kind: str
    name: str
    message: str
    rule: str
    container: Optional[str] = None

    def format(self) -> str:
        where = f"{self.source}: {self.kind}/{self.name}"
        if self.container is not None:
            where += f' container "{self.container}"'
        return f"{where}: {self.message} [{self.rule}]"


def _get(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _pod_spec(doc: Document) -> Optional[Dict[str, Any]]:
    path = POD_SPEC_PATHS.get(doc.kind)
    spec = _get(doc.body, *path) if path else None
    return spec if isinstance(spec, dict) else None


def _containers(pod_spec: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    for field in ("initContainers", "containers"):
        for container in pod_spec.get(field) or []:
            if isinstance(container, dict):
                yield container


def check_no_latest_tag(doc: Document) -> List[Finding]:
    pod_spec = _pod_spec(doc)
    if pod_spec is None:
        return []
    findings = []
    for container in _containers(pod_spec):
        image = container.get("image")
        # An unrendered image belongs to no-image-placeholder alone.
        if not isinstance(image, str) or PLACEHOLDER in image:
            continue
        if resolves_to_latest(image):
            findings.append(Finding(
                doc.source, doc.kind, doc.name,
                f'image "{image}" resolves to :latest; pin an explicit tag or digest',
                "no-latest-tag",
                container=str(container.get("name") or "<unnamed>"),
            ))
    return findings


def _placeholder_paths(obj: Any, path: str) -> Iterator[str]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(key, str) and PLACEHOLDER in key:
                yield child
            yield from _placeholder_paths(value, child)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _placeholder_paths(value, f"{path}[{i}]")
    elif isinstance(obj, str) and PLACEHOLDER in obj:
        yield path


def check_no_image_placeholder(doc: Document) -> List[Finding]:
    return [
        Finding(doc.source, doc.kind, doc.name,
                f"{PLACEHOLDER} left unrendered at {path}", "no-image-placeholder")
        for path in _placeholder_paths(doc.body, "")
    ]


PvcIndex = Dict[Tuple[Optional[str], str], List[str]]


def index_pvcs(docs: List[Document]) -> PvcIndex:
    """Access modes of every PersistentVolumeClaim, keyed by (namespace, name)."""
    return {
        (doc.namespace, doc.name): list(_get(doc.body, "spec", "accessModes") or [])
        for doc in docs
        if doc.kind == "PersistentVolumeClaim"
    }


def check_rwo_requires_recreate(
    doc: Document, pvcs: PvcIndex
) -> Tuple[List[Finding], List[Finding]]:
    """Returns (violations, warnings)."""
    if doc.kind != "Deployment":
        return [], []
    pod_spec = _pod_spec(doc) or {}
    strategy = _get(doc.body, "spec", "strategy", "type") or "RollingUpdate"
    violations, warnings = [], []
    for volume in pod_spec.get("volumes") or []:
        claim = _get(volume, "persistentVolumeClaim", "claimName")
        if not claim:
            continue
        modes = pvcs.get((doc.namespace, claim))
        if modes is None:
            warnings.append(Finding(
                doc.source, doc.kind, doc.name,
                f'PersistentVolumeClaim "{claim}" is not in the input; '
                "cannot check its access mode",
                "rwo-requires-recreate",
            ))
            continue
        rwo = sorted(RWO_MODES.intersection(modes))
        if rwo and strategy != "Recreate":
            violations.append(Finding(
                doc.source, doc.kind, doc.name,
                f'mounts {rwo[0]} PersistentVolumeClaim "{claim}" but '
                f"strategy.type is {strategy}; it must be Recreate",
                "rwo-requires-recreate",
            ))
    return violations, warnings


def check_all(docs: List[Document]) -> Tuple[List[Finding], List[Finding]]:
    """Run every rule over every document. Returns (violations, warnings)."""
    pvcs = index_pvcs(docs)
    violations: List[Finding] = []
    warnings: List[Finding] = []
    for doc in docs:
        violations += check_no_image_placeholder(doc)
        violations += check_no_latest_tag(doc)
        rwo_violations, rwo_warnings = check_rwo_requires_recreate(doc, pvcs)
        violations += rwo_violations
        warnings += rwo_warnings
    return violations, warnings
