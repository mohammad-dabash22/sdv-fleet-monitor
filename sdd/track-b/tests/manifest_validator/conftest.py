import io
import textwrap
from typing import List, NamedTuple, Optional

import pytest

from manifest_validator.cli import main


class Result(NamedTuple):
    code: int
    stderr: str

    @property
    def lines(self) -> List[str]:
        return self.stderr.splitlines()

    @property
    def violations(self) -> List[str]:
        return [l for l in self.lines if not l.startswith(("warning: ", "error: "))]

    @property
    def warnings(self) -> List[str]:
        return [l for l in self.lines if l.startswith("warning: ")]


def run(argv: List[str], stdin: str = "") -> Result:
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin), stderr=err)
    return Result(code, err.getvalue())


def check(manifest: str) -> Result:
    """Validate a manifest passed on stdin."""
    return run(["-"], stdin=textwrap.dedent(manifest))


def deployment(image: str = "registry.example.com/app:1.0", name: str = "app",
               extra_spec: str = "", volumes: str = "") -> str:
    return textwrap.dedent(f"""\
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {name}
        spec:
          {extra_spec}
          selector:
            matchLabels: {{app: {name}}}
          template:
            metadata:
              labels: {{app: {name}}}
            spec:
              containers:
                - name: main
                  image: {image}
              {volumes}
        """)


@pytest.fixture
def write(tmp_path):
    def _write(name: str, content: str):
        path = tmp_path / name
        path.write_text(textwrap.dedent(content))
        return str(path)
    return _write
