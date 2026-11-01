import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import validate_manifests as vm  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def write(tmp_path, text, name="m.yaml"):
    f = tmp_path / name
    f.write_text(textwrap.dedent(text))
    return f


def run(tmp_path, text):
    f = write(tmp_path, text)
    return vm.validate(vm.load_manifests([f]))


def deployment(image="nginx:1.27", strategy="Recreate", replicas=1, claim="data"):
    strategy_yaml = f"strategy: {{type: {strategy}}}" if strategy else ""
    return f"""
        apiVersion: apps/v1
        kind: Deployment
        metadata: {{name: app}}
        spec:
          replicas: {replicas}
          {strategy_yaml}
          template:
            spec:
              containers:
                - name: c
                  image: {image}
              volumes:
                - name: data
                  persistentVolumeClaim: {{claimName: {claim}}}
        """


PVC_RWO = """
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata: {name: data}
    spec: {accessModes: [ReadWriteOnce]}
    ---
"""
PVC_RWX = PVC_RWO.replace("ReadWriteOnce", "ReadWriteMany")


@pytest.mark.parametrize("image", [
    "IMAGE_PLACEHOLDER",
    "postgres:16",
    "docker.io/eclipse/zenoh:1.10.1",
    "registry:5000/team/app:v2",
    "nginx@sha256:" + "a" * 64,
])
def test_pinned_images_pass(image):
    assert vm.image_is_pinned(image)


@pytest.mark.parametrize("image", [
    "nginx", "nginx:latest", "docker.io/library/nginx:latest",
    "registry:5000/team/app", "nginx:", "",
])
def test_unpinned_images_fail(image):
    assert not vm.image_is_pinned(image)


def test_unpinned_image_reported_with_container_name(tmp_path):
    findings, _ = run(tmp_path, PVC_RWO + deployment(image="nginx:latest"))
    assert [(f.rule, f.manifest.name) for f in findings] == [("pinned-image", "app")]
    assert "'c'" in findings[0].message


def test_init_containers_and_cronjobs_are_checked(tmp_path):
    findings, _ = run(tmp_path, """
        kind: CronJob
        metadata: {name: nightly}
        spec:
          jobTemplate:
            spec:
              template:
                spec:
                  initContainers: [{name: init, image: busybox}]
                  containers: [{name: main, image: app:1.0}]
        """)
    assert [f.rule for f in findings] == ["pinned-image"]
    assert "'init'" in findings[0].message


def test_rwo_with_recreate_and_one_replica_passes(tmp_path):
    findings, warnings = run(tmp_path, PVC_RWO + deployment())
    assert findings == [] and warnings == []


def test_rwo_with_rolling_update_fails(tmp_path):
    findings, _ = run(tmp_path, PVC_RWO + deployment(strategy="RollingUpdate"))
    assert [f.rule for f in findings] == ["rwo-disk"]
    assert "Recreate" in findings[0].message


def test_rwo_with_default_strategy_fails(tmp_path):
    findings, _ = run(tmp_path, PVC_RWO + deployment(strategy=None))
    assert [f.rule for f in findings] == ["rwo-disk"]


def test_rwo_with_two_replicas_fails(tmp_path):
    findings, _ = run(tmp_path, PVC_RWO + deployment(replicas=2))
    assert [f.rule for f in findings] == ["rwo-disk"]
    assert "replicas: 2" in findings[0].message


def test_rwx_disk_may_roll_and_scale(tmp_path):
    findings, _ = run(tmp_path, PVC_RWX + deployment(strategy="RollingUpdate", replicas=3))
    assert findings == []


def test_pvc_in_another_file_is_found(tmp_path):
    write(tmp_path, PVC_RWO, "pvc.yaml")
    write(tmp_path, deployment(strategy="RollingUpdate"), "deploy.yaml")
    findings, _ = vm.validate(vm.load_manifests(vm.find_files([tmp_path])))
    assert [f.rule for f in findings] == ["rwo-disk"]


def test_pvc_in_other_namespace_does_not_match(tmp_path):
    pvc = PVC_RWO.replace("{name: data}", "{name: data, namespace: other}")
    findings, warnings = run(tmp_path, pvc + deployment(strategy="RollingUpdate"))
    assert findings == []
    assert len(warnings) == 1 and "'data'" in warnings[0]


def test_main_exit_codes(tmp_path, capsys):
    good = write(tmp_path, PVC_RWO + deployment(), "good.yaml")
    bad = write(tmp_path, PVC_RWO + deployment(image="nginx"), "bad.yaml")
    broken = write(tmp_path, "a: [unclosed", "broken.yaml")
    assert vm.main([str(good)]) == 0
    assert vm.main([str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert vm.main([str(broken)]) == 2
    assert vm.main([str(tmp_path / "empty-dir-does-not-exist")]) == 2


def test_repo_manifests_pass():
    assert vm.main([str(REPO / "k8s")]) == 0
