"""Tests for the `memory brief` CLI subcommand."""
from __future__ import annotations

import os
import subprocess
from datetime import date
from pathlib import Path


BIN = Path(__file__).parent.parent / "bin" / "memory"


def test_cli_brief_prints_output(tmp_path):
    root = tmp_path / "vault"
    (root / ".memory").mkdir(parents=True)
    md = (
        "---\n"
        "name: cli-test\n"
        "description: from cli test\n"
        "type: user\n"
        "subject: user\n"
        "---\n"
        "body\n"
    )
    (root / ".memory" / f"{date.today().isoformat()}-cli-test.md").write_text(md)

    result = subprocess.run(
        [str(BIN), "brief"],
        env={"MEMORY_VAULT_DIR": str(root), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "cli-test" in result.stdout
    assert "from cli test" in result.stdout


def test_cli_brief_no_args_required(tmp_path):
    """`memory brief` takes no positional args; unexpected args should fail."""
    result = subprocess.run(
        [str(BIN), "brief", "extra-arg"],
        env={"MEMORY_VAULT_DIR": str(tmp_path), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
