"""Input: one or more file paths; - reads stdin."""
import subprocess
import sys
from pathlib import Path

from .conftest import deployment, run

REPO = Path(__file__).resolve().parents[2]


def test_reads_a_file_path(write):
    path = write("a.yaml", deployment(image="app:latest"))
    result = run([path])
    assert result.code == 1
    assert result.violations[0].startswith(f"{path}: Deployment/app")


def test_reads_several_file_paths(write):
    a = write("a.yaml", deployment(image="app:latest", name="a"))
    b = write("b.yaml", deployment(image="app:latest", name="b"))
    result = run([a, b])
    assert result.code == 1
    assert len(result.violations) == 2


def test_dash_reads_stdin():
    result = run(["-"], stdin=deployment(image="app:latest"))
    assert result.code == 1
    assert result.violations[0].startswith("<stdin>: Deployment/app")


def test_clean_stdin_passes():
    assert run(["-"], stdin=deployment()).code == 0


def test_runs_as_module_with_stdin():
    proc = subprocess.run(
        [sys.executable, "-m", "manifest_validator", "-"],
        input=deployment(image="app:latest"), capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 1
    assert "[no-latest-tag]" in proc.stderr
