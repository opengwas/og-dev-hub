#!/usr/bin/env python3
"""Nothing the site's code writes falls back to the host's /tmp (og-dev-hub#7).

Everything the site writes lives under /data/opengwasdb (`paths.WORK_ROOT`,
CONTRIBUTING's Worktrees rule in opengwasdb-stores), so every `tempfile` scratch
call in `src/project_site/` names its `dir=`: without one, Python picks `$TMPDIR`,
else `/tmp`. opengwasdb-stores enforced this over `src/project_site/` until the
site moved here (its `tests/packaging/test_layout.py`, `SCRATCH_TREES`); this is
the same check. A test may use `tempfile` freely.

Run from the repository root:
    python3 tests/project-site/test_scratch.py
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRATCH_TREE = REPO_ROOT / "src" / "project_site"

#: The `tempfile` factories: each writes where `dir=` says, and to the host's `/tmp` without it.
TEMP_FACTORIES = frozenset({
    "TemporaryDirectory", "mkdtemp", "mkstemp", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile",
})


def _temp_factory(func: ast.expr) -> str | None:
    """The factory a call names, for `tempfile.mkdtemp(...)` and a bare `mkdtemp(...)` alike."""
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "tempfile":
        return func.attr if func.attr in TEMP_FACTORIES else None
    if isinstance(func, ast.Name) and func.id in TEMP_FACTORIES:
        return func.id
    return None


def missing_dir_calls(relative: str, source: str) -> list[str]:
    """Every `tempfile` scratch call in one file that names no `dir=`."""
    found = []
    for node in ast.walk(ast.parse(source, filename=relative)):
        if not isinstance(node, ast.Call):
            continue
        factory = _temp_factory(node.func)
        if factory and not any(keyword.arg == "dir" for keyword in node.keywords):
            found.append(f"{relative}:{node.lineno}: tempfile.{factory} without dir=")
    return found


class ScratchTest(unittest.TestCase):
    def test_no_scratch_call_falls_back_to_the_hosts_tmp(self) -> None:
        found = []
        for path in sorted(SCRATCH_TREE.rglob("*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            found += missing_dir_calls(relative, path.read_text(encoding="utf-8"))
        self.assertEqual(found, [], "name a scratch root under /data for every tempfile call")

    def test_the_scratch_scanner_finds_what_it_looks_for(self) -> None:
        self.assertEqual(
            missing_dir_calls("src/project_site/planted.py", (
                "import tempfile\n"
                "from tempfile import mkdtemp\n"
                "a = tempfile.mkdtemp(prefix='x')\n"
                "b = tempfile.TemporaryDirectory(prefix='y')\n"
                "c = mkdtemp(prefix='z')\n"
                "d = tempfile.mkdtemp(prefix='ok', dir=root)\n"
                "e = tempfile.NamedTemporaryFile(delete=False)\n"
                "f = tempfile.TemporaryFile(dir=root)\n"
                "g = tempfile._get_candidate_names()\n"
            )),
            [
                "src/project_site/planted.py:3: tempfile.mkdtemp without dir=",
                "src/project_site/planted.py:4: tempfile.TemporaryDirectory without dir=",
                "src/project_site/planted.py:5: tempfile.mkdtemp without dir=",
                "src/project_site/planted.py:7: tempfile.NamedTemporaryFile without dir=",
            ],
        )


if __name__ == "__main__":
    unittest.main()
