"""The repo's k8s/ manifests pass once rendered and fail while unrendered."""
from pathlib import Path

import pytest

from .conftest import run

K8S = Path(__file__).resolve().parents[2] / "k8s"
MANIFESTS = sorted(K8S.glob("*.yaml"))
PINNED = "registry.example.com/sdv:1.0.0"


def test_manifests_exist():
    assert MANIFESTS


@pytest.mark.parametrize("path", MANIFESTS, ids=lambda p: p.name)
def test_rendered_manifest_passes(path):
    # The same substitution Jenkins does: sed "s|IMAGE_PLACEHOLDER|$IMAGE|"
    rendered = path.read_text().replace("IMAGE_PLACEHOLDER", PINNED)
    result = run(["-"], stdin=rendered)
    assert (result.code, result.stderr) == (0, "")


@pytest.mark.parametrize(
    "path", [p for p in MANIFESTS if "image: IMAGE_PLACEHOLDER" in p.read_text()],
    ids=lambda p: p.name,
)
def test_unrendered_manifest_fails_placeholder_rule(path):
    result = run([str(path)])
    assert result.code == 1
    assert all("[no-image-placeholder]" in l for l in result.violations)
