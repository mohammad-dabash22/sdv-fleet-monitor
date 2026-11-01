"""Command line entry point: python -m manifest_validator PATH [PATH ...] | -"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, TextIO

import yaml

from .rules import Document, check_all

EXIT_OK = 0
EXIT_VIOLATIONS = 1
EXIT_INPUT_ERROR = 2

STDIN_NAME = "<stdin>"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m manifest_validator",
        description="Fail when a rendered Kubernetes manifest breaks a deployment rule.",
    )
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="manifest file to check, or - for stdin")
    return parser


def _read(path: str, stdin: TextIO) -> str:
    if path == "-":
        return stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(
    argv: Optional[List[str]] = None,
    stdin: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    stdin = stdin or sys.stdin
    stderr = stderr or sys.stderr
    args = _parser().parse_args(argv)

    docs: List[Document] = []
    input_error = False
    for path in args.paths:
        source = STDIN_NAME if path == "-" else path
        try:
            loaded = list(yaml.safe_load_all(_read(path, stdin)))
        except (OSError, UnicodeDecodeError) as e:
            print(f"error: {source}: cannot read: {e}", file=stderr)
            input_error = True
            continue
        except yaml.YAMLError as e:
            print(f"error: {source}: invalid YAML: {e}", file=stderr)
            input_error = True
            continue
        docs += [Document(source, body) for body in loaded if isinstance(body, dict)]

    violations, warnings = check_all(docs)
    for warning in warnings:
        print(f"warning: {warning.format()}", file=stderr)
    for violation in violations:
        print(violation.format(), file=stderr)

    if input_error:
        return EXIT_INPUT_ERROR
    return EXIT_VIOLATIONS if violations else EXIT_OK
