"""no-latest-tag covers containers and initContainers of every workload kind."""
import textwrap

import pytest

from .conftest import check

POD_SPEC = """\
initContainers:
  - name: init
    image: busybox
containers:
  - name: main
    image: app:latest
"""


def _indent(text, spaces):
    return textwrap.indent(text, " " * spaces)


def _manifest(kind):
    if kind == "Pod":
        body = "spec:\n" + _indent(POD_SPEC, 2)
    elif kind == "CronJob":
        body = ("spec:\n  schedule: '* * * * *'\n  jobTemplate:\n    spec:\n"
                "      template:\n        spec:\n" + _indent(POD_SPEC, 10))
    else:
        body = "spec:\n  template:\n    spec:\n" + _indent(POD_SPEC, 6)
    return f"kind: {kind}\nmetadata:\n  name: w\n" + body


@pytest.mark.parametrize("kind", [
    "Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob",
])
def test_containers_and_init_containers_are_checked(kind):
    result = check(_manifest(kind))
    assert result.code == 1
    assert len(result.violations) == 2
    assert f'{kind}/w container "init": image "busybox"' in result.violations[0]
    assert f'{kind}/w container "main": image "app:latest"' in result.violations[1]


def test_non_workload_kinds_are_not_image_checked():
    result = check("kind: ConfigMap\nmetadata:\n  name: c\ndata:\n  image: app:latest\n")
    assert result.code == 0
