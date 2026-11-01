"""Rule no-latest-tag: images tagged :latest or untagged are violations."""
import pytest

from .conftest import check, deployment


@pytest.mark.parametrize("image", [
    "app:latest",
    "registry.example.com/team/app:latest",
])
def test_latest_tag_is_a_violation(image):
    result = check(deployment(image=image))
    assert result.code == 1
    assert result.violations == [
        f'<stdin>: Deployment/app container "main": image "{image}" resolves to '
        f":latest; pin an explicit tag or digest [no-latest-tag]"
    ]


@pytest.mark.parametrize("image", ["postgres", "registry.example.com/team/app"])
def test_untagged_image_is_a_violation(image):
    result = check(deployment(image=image))
    assert result.code == 1
    assert "[no-latest-tag]" in result.violations[0]


@pytest.mark.parametrize("image", ["postgres:16", "docker.io/eclipse/zenoh:1.10.1"])
def test_explicit_tag_passes(image):
    assert check(deployment(image=image)).code == 0
