"""Registry ports are not tags; digests pin the image."""
import pytest

from manifest_validator.images import parse_image, resolves_to_latest


@pytest.mark.parametrize("ref, expected", [
    ("registry:5000/app", True),
    ("registry:5000/app:1.2", False),
    ("localhost:5000/team/app:latest", True),
    ("app", True),
    ("app:latest", True),
    ("app:1.0", False),
])
def test_tag_detection(ref, expected):
    assert resolves_to_latest(ref) is expected


@pytest.mark.parametrize("ref", [
    "app@sha256:" + "a" * 64,
    "app:latest@sha256:" + "a" * 64,
    "registry:5000/app@sha256:" + "a" * 64,
])
def test_digest_pins_the_image(ref):
    assert resolves_to_latest(ref) is False


def test_parse_splits_registry_port_from_tag():
    image = parse_image("registry:5000/team/app:1.2@sha256:abc")
    assert image.repository == "registry:5000/team/app"
    assert image.tag == "1.2"
    assert image.digest == "sha256:abc"
