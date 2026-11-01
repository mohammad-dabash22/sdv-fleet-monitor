---
name: Kubernetes Manifest Validator
description: Pre-deploy gate that fails the build when a rendered Kubernetes manifest breaks a deployment rule
targets:
  - ../manifest_validator/**/*.py
---

# Kubernetes Manifest Validator

A Python CLI (PyYAML) that Jenkins runs on **rendered** manifests: after
`sed "s|IMAGE_PLACEHOLDER|$IMAGE|"` and before `kubectl apply`. It checks what
is actually applied, never talks to a cluster, and fails the build on any rule
violation.

```text
python -m manifest_validator PATH [PATH ...]
python -m manifest_validator -            # read the manifest from stdin

exit 0  no violations (warnings allowed)
exit 1  one or more violations
exit 2  unreadable input or invalid YAML
```

## Input

- Accepts one or more file paths; `-` reads from stdin
  `[@test] ../tests/manifest_validator/test_cli_input.py`
- A source may hold several YAML documents separated by `---`; every document
  is checked, and empty documents (e.g. a leading `---` after comments) are ignored
  `[@test] ../tests/manifest_validator/test_multi_document.py`
- A missing or unreadable file, or YAML that fails to parse, prints an error
  naming the source to stderr and exits 2, whatever else was found
  `[@test] ../tests/manifest_validator/test_input_errors.py`

## Rule `no-latest-tag`

No container image may resolve to `:latest`. With an unchanged tag
`kubectl apply` reports "unchanged" and the new image is never rolled out.

- An image tagged `:latest` is a violation
  `[@test] ../tests/manifest_validator/test_no_latest_tag.py`
- An image with no tag (`postgres`, `registry.example.com/team/app`) defaults to
  `:latest` and is a violation
  `[@test] ../tests/manifest_validator/test_no_latest_tag.py`
- A registry port is not a tag: `registry:5000/app` is untagged (violation),
  `registry:5000/app:1.2` is tagged (passes)
  `[@test] ../tests/manifest_validator/test_image_reference_parsing.py`
- An image pinned by digest (`app@sha256:…`, including `app:latest@sha256:…`) passes
  `[@test] ../tests/manifest_validator/test_image_reference_parsing.py`
- Both `containers` and `initContainers` are checked, in the pod spec of every
  workload kind: Pod, Deployment, StatefulSet, DaemonSet, ReplicaSet, Job, and
  CronJob (`spec.jobTemplate.spec.template.spec`)
  `[@test] ../tests/manifest_validator/test_workload_kinds.py`

## Rule `no-image-placeholder`

A manifest that still contains `IMAGE_PLACEHOLDER` was not rendered and must not
be applied.

- Any parsed value (key or scalar, at any depth) containing the text
  `IMAGE_PLACEHOLDER` is a violation, reported against the resource that
  contains it; YAML comments are not values and are ignored
  `[@test] ../tests/manifest_validator/test_no_image_placeholder.py`
- An image of `IMAGE_PLACEHOLDER` is reported only by this rule, not also as
  untagged by `no-latest-tag`
  `[@test] ../tests/manifest_validator/test_no_image_placeholder.py`

## Rule `rwo-requires-recreate`

A Deployment whose pod mounts a ReadWriteOnce PersistentVolumeClaim must set
`spec.strategy.type: Recreate`; under a rolling update the second pod can never
attach the disk.

- A Deployment mounting a PVC whose `accessModes` include `ReadWriteOnce` or
  `ReadWriteOncePod` without `strategy.type: Recreate` is a violation; a missing
  `strategy` counts, since Kubernetes defaults to `RollingUpdate`
  `[@test] ../tests/manifest_validator/test_rwo_requires_recreate.py`
- The same Deployment with `strategy.type: Recreate` passes, as does a Deployment
  mounting only `ReadWriteMany` / `ReadOnlyMany` PVCs
  `[@test] ../tests/manifest_validator/test_rwo_requires_recreate.py`
- PVCs are matched to `volumes[].persistentVolumeClaim.claimName` by name and
  namespace across all sources given in one run; an unset namespace matches only
  another unset namespace
  `[@test] ../tests/manifest_validator/test_pvc_resolution.py`
- If a mounted PVC is not defined in the input, a warning is printed and the
  rule is not applied to it; on its own this keeps exit 0
  `[@test] ../tests/manifest_validator/test_pvc_resolution.py`

## Output

- Every violation in every document is reported; checking does not stop at the
  first one
  `[@test] ../tests/manifest_validator/test_output_format.py`
- Each violation is one line on stderr:
  `<source>: <Kind>/<name> container "<c>": <message> [<rule-id>]`, where the
  `container "<c>"` part is omitted for rules not about a container, and
  `<source>` is the path or `<stdin>`
  `[@test] ../tests/manifest_validator/test_output_format.py`
- Warnings are one line on stderr prefixed `warning: ` and never change the exit code
  `[@test] ../tests/manifest_validator/test_output_format.py`
- Exit codes: 0 when clean, 1 on any violation, 2 on input errors (2 wins over 1)
  `[@test] ../tests/manifest_validator/test_exit_codes.py`

## The repo's own manifests

- Each file in `k8s/`, rendered with a pinned image such as
  `registry.example.com/sdv:1.0.0`, passes with exit 0; the same files
  unrendered fail `no-image-placeholder`
  `[@test] ../tests/manifest_validator/test_repo_manifests.py`

## Out of scope

Other deployment rules, Helm/Kustomize rendering, changes to the Jenkins
pipeline, and any live-cluster access.
