"""REQ-040: comments and docstrings describe the code as it is now.

The MVP was full of "NEXT PHASE" and "fake today" notes about work that has since been done (Zenoh,
Kuksa, PostgreSQL, Ankaios). They told readers, graders and AI agents the wrong thing about the code.
Notes about work that is still to come say "V2" or name the spec entry instead.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTDATED = re.compile(r"NEXT PHASE|next phase|fake today|Today:|TODAY|still fakes until")
SKIP = ("specs/", "docs/", "sdd/", ".claude/", "skills-vendor/", "measurements/", "skills-CHANGELOG.md",
        "CLAUDE.md", "tests/test_docs.py")


def tracked_text_files():
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    for name in names:
        if name.startswith(SKIP) or not name.endswith((".py", ".js", ".html", ".css", ".sql", ".yml", ".yaml",
                                                       ".md", ".bat", ".sh", "Dockerfile", "Jenkinsfile")):
            continue
        yield name, (ROOT / name).read_text(encoding="utf-8", errors="replace")


def test_req_040_no_outdated_next_phase_notes():
    found = [f"{name}:{i}: {line.strip()}" for name, text in tracked_text_files()
             for i, line in enumerate(text.splitlines(), 1) if OUTDATED.search(line)]
    assert found == [], "\n".join(found)


def test_req_040_dead_code_is_gone():
    detector = (ROOT / "vehicle/hazard_detector/main.py").read_text(encoding="utf-8")
    analytics = (ROOT / "cloud/app/analytics.py").read_text(encoding="utf-8")
    assert "def stop(self, client" not in detector        # never called: run() owns the client
    assert "self.costs" not in analytics                   # never read: route economics are V2
