"""PVC lookup across sources by name and namespace; missing PVCs warn only."""
from .conftest import check, deployment, run

VOLUMES = """volumes:
                - name: data
                  persistentVolumeClaim:
                    claimName: data"""

RWO_PVC = """\
kind: PersistentVolumeClaim
metadata:
  name: data
  {namespace}
spec:
  accessModes: [ReadWriteOnce]
---
"""


def test_pvc_in_another_source_is_resolved(write):
    pvc_file = write("pvc.yaml", RWO_PVC.format(namespace=""))
    deploy_file = write("deploy.yaml", deployment(volumes=VOLUMES))
    result = run([pvc_file, deploy_file])
    assert result.code == 1
    assert result.warnings == []
    assert result.violations[0].startswith(f"{deploy_file}: Deployment/app:")


def test_pvc_in_another_namespace_does_not_match():
    result = check(RWO_PVC.format(namespace="namespace: other") + deployment(volumes=VOLUMES))
    assert result.code == 0
    assert len(result.warnings) == 1


def test_pvc_in_same_namespace_matches():
    manifest = RWO_PVC.format(namespace="namespace: prod") + deployment(volumes=VOLUMES).replace(
        "  name: app\n", "  name: app\n  namespace: prod\n", 1)
    assert check(manifest).code == 1


def test_missing_pvc_warns_and_exits_0():
    result = check(deployment(volumes=VOLUMES))
    assert result.code == 0
    assert result.violations == []
    assert result.warnings == [
        'warning: <stdin>: Deployment/app: PersistentVolumeClaim "data" is not in the '
        "input; cannot check its access mode [rwo-requires-recreate]"
    ]
