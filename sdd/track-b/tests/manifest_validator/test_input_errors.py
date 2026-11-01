"""Unreadable input or invalid YAML exits 2 and names the source."""
from .conftest import check, deployment, run


def test_missing_file_exits_2(tmp_path):
    missing = str(tmp_path / "nope.yaml")
    result = run([missing])
    assert result.code == 2
    assert result.lines[0].startswith(f"error: {missing}:")


def test_invalid_yaml_exits_2():
    result = check("kind: Deployment\nmetadata: [unclosed\n")
    assert result.code == 2
    assert result.lines[0].startswith("error: <stdin>: invalid YAML")


def test_input_error_wins_over_violations(write, tmp_path):
    bad = write("bad.yaml", deployment(image="app:latest"))
    result = run([bad, str(tmp_path / "nope.yaml")])
    assert result.code == 2
    assert any("[no-latest-tag]" in l for l in result.violations)
