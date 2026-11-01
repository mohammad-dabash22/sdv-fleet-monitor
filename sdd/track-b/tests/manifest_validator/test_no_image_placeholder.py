"""Rule no-image-placeholder: unrendered values fail; comments are ignored."""
from .conftest import check, deployment


def test_placeholder_image_is_a_violation():
    result = check(deployment(image="IMAGE_PLACEHOLDER"))
    assert result.code == 1
    assert result.violations == [
        "<stdin>: Deployment/app: IMAGE_PLACEHOLDER left unrendered at "
        "spec.template.spec.containers[0].image [no-image-placeholder]"
    ]


def test_placeholder_image_is_not_also_reported_as_untagged():
    result = check(deployment(image="IMAGE_PLACEHOLDER"))
    assert not any("[no-latest-tag]" in l for l in result.violations)


def test_placeholder_anywhere_in_a_value_is_a_violation():
    manifest = """\
        kind: ConfigMap
        metadata:
          name: c
        data:
          IMAGE_PLACEHOLDER_KEY: x
          image: "repo/IMAGE_PLACEHOLDER:1"
        """
    result = check(manifest)
    assert result.code == 1
    assert [l.split(" at ")[1] for l in result.violations] == [
        "data.IMAGE_PLACEHOLDER_KEY [no-image-placeholder]",
        "data.image [no-image-placeholder]",
    ]


def test_placeholder_in_comments_is_ignored():
    manifest = "# sed s|IMAGE_PLACEHOLDER|$IMAGE|\n" + deployment()
    assert check(manifest).code == 0
