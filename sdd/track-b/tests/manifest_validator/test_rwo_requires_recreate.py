"""Rule rwo-requires-recreate: a Deployment mounting an RWO PVC must use Recreate."""
import pytest

from .conftest import check, deployment

VOLUMES = """volumes:
                - name: data
                  persistentVolumeClaim:
                    claimName: data"""


def pvc(mode: str, name: str = "data") -> str:
    return f"""\
kind: PersistentVolumeClaim
metadata:
  name: {name}
spec:
  accessModes: [{mode}]
---
"""


@pytest.mark.parametrize("mode", ["ReadWriteOnce", "ReadWriteOncePod"])
def test_rwo_without_strategy_is_a_violation(mode):
    result = check(pvc(mode) + deployment(volumes=VOLUMES))
    assert result.code == 1
    assert result.violations == [
        f'<stdin>: Deployment/app: mounts {mode} PersistentVolumeClaim "data" but '
        "strategy.type is RollingUpdate; it must be Recreate [rwo-requires-recreate]"
    ]


def test_rwo_with_rolling_update_is_a_violation():
    manifest = pvc("ReadWriteOnce") + deployment(
        volumes=VOLUMES, extra_spec="strategy: {type: RollingUpdate}")
    result = check(manifest)
    assert result.code == 1
    assert "[rwo-requires-recreate]" in result.violations[0]


def test_rwo_with_recreate_passes():
    manifest = pvc("ReadWriteOnce") + deployment(
        volumes=VOLUMES, extra_spec="strategy: {type: Recreate}")
    result = check(manifest)
    assert result.code == 0
    assert result.stderr == ""


@pytest.mark.parametrize("mode", ["ReadWriteMany", "ReadOnlyMany"])
def test_shared_access_modes_pass_with_rolling_update(mode):
    assert check(pvc(mode) + deployment(volumes=VOLUMES)).code == 0
