"""REQ-037, REQ-027 AC4: the deployment files agree with the code.

Jenkins (Groovy) and Kubernetes cannot run here, so these tests read the files instead: the topic
and subscription names Jenkins creates are the ones the bridge and the Dataflow job use, and the
bridge container is configured for real Pub/Sub and the Zenoh router in its own pod.
"""

import re
from pathlib import Path

import yaml

from cloud.pipeline.pubsub import SUBSCRIPTIONS, TOPICS

ROOT = Path(__file__).resolve().parents[1]


def test_req_037_jenkins_creates_the_topics_and_subscriptions_the_code_uses():
    jenkinsfile = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    kinds = re.search(r"for kind in ([a-z ]+); do", jenkinsfile).group(1).split()
    assert sorted(f"fleet-{k}" for k in kinds) == sorted(TOPICS.values())
    assert sorted(f"fleet-{k}-beam" for k in kinds) == sorted(SUBSCRIPTIONS.values())


def test_req_037_pubsub_stage_cannot_stop_the_deploy():
    jenkinsfile = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    stages = re.findall(r"stage\('([a-z]+)'\)", jenkinsfile)
    assert stages == ["test", "containerize", "database", "pubsub", "deploy", "record", "service", "dataflow"]
    pubsub = jenkinsfile.split("stage('pubsub')")[1].split("stage('deploy')")[0]
    assert "catchError(buildResult: 'UNSTABLE'" in pubsub


def test_req_037_dataflow_never_starts_on_a_merge():
    """D-7: a merge must not start a billed streaming job; only a manual "Build with Parameters" does."""
    jenkinsfile = (ROOT / "Jenkinsfile").read_text(encoding="utf-8")
    choices = re.search(r"choice\(name: 'DATAFLOW', choices: \[([^\]]+)\]", jenkinsfile).group(1)
    assert [c.strip(" '") for c in choices.split(",")][0] == "none"          # the default for webhook/poll builds
    stage = jenkinsfile.split("stage('dataflow')")[1]
    assert "when { expression { params.DATAFLOW != 'none' } }" in stage
    assert "tools.dataflow_job start" in stage and "tools.dataflow_job drain" in stage


def test_req_027_bridge_container_in_the_cloud_pod():
    docs = [d for d in yaml.safe_load_all((ROOT / "deploy/k8s/cloud.yaml").read_text(encoding="utf-8")) if d]
    pod = next(d for d in docs if d["kind"] == "Deployment")["spec"]["template"]["spec"]
    bridge = next(c for c in pod["containers"] if c["name"] == "bridge")
    env = {e["name"]: e["value"] for e in bridge["env"]}
    assert bridge["command"][-1] == "cloud.pipeline.bridge"
    assert env == {"PUBSUB": "gcp", "TRANSPORT": "zenoh", "ZENOH_ENDPOINT": "tcp/127.0.0.1:7447"}
    cloud = next(c for c in pod["containers"] if c["name"] == "cloud")
    assert bridge["image"] == cloud["image"] == "IMAGE_PLACEHOLDER"   # same image, replaced by Jenkins


def test_req_032_fleet_db_has_an_internal_service_for_dataflow():
    docs = [d for d in yaml.safe_load_all((ROOT / "deploy/k8s/fleet-db.yaml").read_text(encoding="utf-8")) if d]
    services = {d["metadata"]["name"]: d for d in docs if d["kind"] == "Service"}
    assert services["sdv-fleet-db"]["spec"]["type"] == "ClusterIP"          # unchanged for the pod
    internal = services["sdv-fleet-db-internal"]
    assert internal["spec"]["type"] == "LoadBalancer"
    assert internal["metadata"]["annotations"]["networking.gke.io/load-balancer-type"] == "Internal"
