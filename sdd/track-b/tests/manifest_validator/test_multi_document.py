"""Every document in a multi-document source is checked; empty ones are ignored."""
from .conftest import check, deployment


def test_every_document_is_checked():
    manifest = (
        deployment(image="first:1.0", name="first")
        + "---\n"
        + deployment(image="second:latest", name="second")
    )
    result = check(manifest)
    assert result.code == 1
    assert len(result.violations) == 1
    assert "Deployment/second" in result.violations[0]


def test_empty_documents_are_ignored():
    manifest = "# leading comment\n---\n---\n" + deployment() + "---\n"
    result = check(manifest)
    assert result.code == 0
    assert result.stderr == ""
