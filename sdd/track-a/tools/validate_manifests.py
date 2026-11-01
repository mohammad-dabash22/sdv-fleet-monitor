#!/usr/bin/env python3
"""Check Kubernetes manifests against our deployment rules before they are applied.

Rules:
  pinned-image    Every container image has an explicit tag (not :latest) or a
                  digest. IMAGE_PLACEHOLDER is allowed: Jenkins replaces it with
                  the image it just built.
  rwo-disk        A Deployment that mounts a ReadWriteOnce PVC must use the
                  Recreate strategy and run 1 replica. With RollingUpdate or more
                  replicas, a second pod waits forever for a disk it can't attach.

Usage:
  validate_manifests.py [PATH ...]    files or directories (default: k8s/)

Exit codes: 0 all rules pass, 1 a rule is broken, 2 a manifest could not be read.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

IMAGE_PLACEHOLDER = "IMAGE_PLACEHOLDER"
RWO_MODES = {"ReadWriteOnce", "ReadWriteOncePod"}

# Kinds that run containers, and how to reach their pod spec.
POD_SPEC_PATHS = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "ReplicaSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


@dataclass
class Manifest:
    path: Path
    doc: dict

    @property
    def kind(self):
        return self.doc.get("kind", "?")

    @property
    def name(self):
        return (self.doc.get("metadata") or {}).get("name", "?")

    @property
    def namespace(self):
        return (self.doc.get("metadata") or {}).get("namespace", "default")

    def __str__(self):
        return f"{self.path}: {self.kind}/{self.name}"


@dataclass
class Finding:
    manifest: Manifest
    rule: str
    message: str

    def __str__(self):
        return f"{self.manifest}: [{self.rule}] {self.message}"


def find_files(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix in (".yaml", ".yml"))
        else:
            files.append(p)
    return files


def load_manifests(files):
    manifests = []
    for f in files:
        with open(f) as fh:
            for doc in yaml.safe_load_all(fh):
                if isinstance(doc, dict):  # skip empty documents between ---
                    manifests.append(Manifest(f, doc))
    return manifests


def dig(doc, path):
    for key in path:
        if not isinstance(doc, dict):
            return None
        doc = doc.get(key)
    return doc


def pod_spec(m):
    path = POD_SPEC_PATHS.get(m.kind)
    return dig(m.doc, path) if path else None


def image_is_pinned(image):
    if image == IMAGE_PLACEHOLDER or "@" in image:  # placeholder or digest
        return True
    # The tag follows the last ':' in the last path segment, so a registry
    # port (registry:5000/app) is not mistaken for a tag.
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return False
    return last.rsplit(":", 1)[1] not in ("", "latest")


def check_pinned_images(m, _context):
    spec = pod_spec(m)
    if not spec:
        return
    for field in ("initContainers", "containers", "ephemeralContainers"):
        for c in spec.get(field) or []:
            image = c.get("image", "")
            if not image_is_pinned(image):
                yield Finding(
                    m, "pinned-image",
                    f"container {c.get('name', '?')!r} uses image {image!r}; "
                    "pin a version tag or digest (not :latest)",
                )


def check_rwo_disk(m, context):
    if m.kind != "Deployment":
        return
    spec = m.doc.get("spec") or {}
    for vol in dig(spec, ("template", "spec", "volumes")) or []:
        claim = dig(vol, ("persistentVolumeClaim", "claimName"))
        if not claim:
            continue
        pvc = context["pvcs"].get((m.namespace, claim))
        if pvc is None:
            context["warnings"].append(
                f"{m}: PVC {claim!r} is not in the checked manifests; "
                "can't tell if it is ReadWriteOnce"
            )
            continue
        if not RWO_MODES & set(dig(pvc.doc, ("spec", "accessModes")) or []):
            continue
        strategy = dig(spec, ("strategy", "type")) or "RollingUpdate"
        if strategy != "Recreate":
            yield Finding(
                m, "rwo-disk",
                f"mounts ReadWriteOnce PVC {claim!r} but strategy is {strategy}; "
                "use strategy.type: Recreate",
            )
        replicas = spec.get("replicas", 1)
        if replicas != 1:
            yield Finding(
                m, "rwo-disk",
                f"mounts ReadWriteOnce PVC {claim!r} but has replicas: {replicas}; "
                "only 1 pod can attach the disk",
            )


RULES = [check_pinned_images, check_rwo_disk]


def validate(manifests):
    """Return (findings, warnings) for the given manifests."""
    context = {
        "pvcs": {
            (m.namespace, m.name): m
            for m in manifests if m.kind == "PersistentVolumeClaim"
        },
        "warnings": [],
    }
    findings = [f for m in manifests for rule in RULES for f in rule(m, context)]
    return findings, context["warnings"]


def main(argv):
    files = find_files(argv or ["k8s"])
    if not files:
        print("no manifests found", file=sys.stderr)
        return 2
    try:
        manifests = load_manifests(files)
    except (OSError, yaml.YAMLError) as e:
        print(f"could not read manifests: {e}", file=sys.stderr)
        return 2

    findings, warnings = validate(manifests)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for f in findings:
        print(f"FAIL {f}")
    print(f"checked {len(manifests)} resources in {len(files)} files: "
          f"{len(findings)} violation(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
