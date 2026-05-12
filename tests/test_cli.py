"""Tests for lib/cli.py - invoke as a subprocess against a tmp vault."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CLI = ROOT / "lib" / "cli.py"


def _run(args, vault_dir, stdin=""):
    env = os.environ.copy()
    env["MEMORY_VAULT_DIR"] = str(vault_dir)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def test_write_reads_body_from_stdin_and_prints_path(tmp_path):
    result = _run(
        ["write", "--type", "reference", "--name", "alpha",
         "--subject", "docs", "--description", "first note"],
        vault_dir=tmp_path,
        stdin="hello body\n",
    )
    assert result.returncode == 0, result.stderr
    stored = result.stdout.strip()
    assert stored, "expected stored path on stdout"
    p = Path(stored)
    assert p.exists(), f"stored path does not exist: {stored}"
    assert "hello body" in p.read_text()


def test_list_outputs_entries(tmp_path):
    _run(
        ["write", "--type", "reference", "--name", "alpha",
         "--subject", "docs", "--description", "first"],
        vault_dir=tmp_path, stdin="a\n",
    )
    _run(
        ["write", "--type", "project", "--name", "beta",
         "--subject", "docs", "--description", "second"],
        vault_dir=tmp_path, stdin="b\n",
    )
    result = _run(["list"], vault_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "alpha" in out and "beta" in out
    assert "reference:docs:alpha" in out
    assert "project:docs:beta" in out


def test_get_outputs_entry_markdown(tmp_path):
    _run(
        ["write", "--type", "reference", "--name", "alpha",
         "--subject", "docs", "--description", "first note"],
        vault_dir=tmp_path, stdin="body content here\n",
    )
    result = _run(
        ["get", "--name", "alpha", "--type", "reference"],
        vault_dir=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.startswith("---\n")
    assert "name: alpha" in out
    assert "type: reference" in out
    assert "subject: docs" in out
    assert "description: first note" in out
    assert "body content here" in out


def test_get_missing_entry_prints_not_found_and_exits_1(tmp_path):
    result = _run(
        ["get", "--name", "nope", "--type", "reference"],
        vault_dir=tmp_path,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_rebuild_index_prints_count(tmp_path):
    _run(
        ["write", "--type", "reference", "--name", "alpha",
         "--subject", "docs", "--description", "first"],
        vault_dir=tmp_path, stdin="a\n",
    )
    result = _run(["rebuild-index"], vault_dir=tmp_path)
    assert result.returncode == 0, result.stderr
    count = int(result.stdout.strip())
    assert count >= 1


def test_invalid_type_exits_nonzero(tmp_path):
    result = _run(
        ["write", "--type", "bogus", "--name", "x",
         "--subject", "docs", "--description", "d"],
        vault_dir=tmp_path, stdin="body\n",
    )
    assert result.returncode != 0


def test_unknown_subcommand_exits_nonzero(tmp_path):
    result = _run(["frobnicate"], vault_dir=tmp_path)
    assert result.returncode != 0
