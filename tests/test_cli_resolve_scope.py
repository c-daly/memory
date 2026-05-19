"""Tests for the `memory resolve-scope <subject>` CLI subcommand."""
from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path


BIN = Path(__file__).parent.parent / "bin" / "memory"


def test_cli_resolve_scope_prints_entries(tmp_path):
    root = tmp_path / "vault"
    (root / "10-projects" / "alpha" / ".memory").mkdir(parents=True)
    md = (
        "---\n"
        "name: scope-test\n"
        "description: alpha-scoped entry\n"
        "type: project\n"
        "subject: alpha\n"
        "---\n"
        "body\n"
    )
    (root / "10-projects" / "alpha" / ".memory" / f"{date.today().isoformat()}-scope-test.md").write_text(md)

    result = subprocess.run(
        [str(BIN), "resolve-scope", "alpha"],
        env={"MEMORY_VAULT_DIR": str(root), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "scope-test" in result.stdout


def test_cli_resolve_scope_requires_subject(tmp_path):
    result = subprocess.run(
        [str(BIN), "resolve-scope"],
        env={"MEMORY_VAULT_DIR": str(tmp_path), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
