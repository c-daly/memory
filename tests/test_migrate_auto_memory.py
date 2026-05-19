"""Tests for scripts/migrate-auto-memory.sh."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent.parent / "scripts" / "migrate-auto-memory.sh"
FIXTURE = Path(__file__).parent / "fixtures" / "auto_memory_sample"


def _make_vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "10-projects" / "memory").mkdir(parents=True)
    return root


def test_dry_run_lists_proposals_without_writing(tmp_path):
    """DRY=1 prints proposed migrations and does NOT call bin/memory write."""
    vault = _make_vault(tmp_path)
    auto = tmp_path / "auto-memory"
    shutil.copytree(FIXTURE, auto)

    result = subprocess.run(
        [str(SCRIPT)],
        env={
            "DRY": "1",
            "AUTO_MEMORY_DIR": str(auto),
            "MEMORY_VAULT_DIR": str(vault),
            "PATH": os.environ["PATH"],
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "memory-plugin-vault-is-store" in result.stdout
    assert "memories-close-to-entity" in result.stdout
    assert "some-other" in result.stdout
    memory_dir = vault / "10-projects" / "memory" / ".memory"
    assert not memory_dir.exists() or not any(memory_dir.iterdir())


def test_batch_mode_writes_entries(tmp_path):
    """--batch accepts heuristic suggestions without prompting."""
    vault = _make_vault(tmp_path)
    (vault / ".memory").mkdir(parents=True)
    auto = tmp_path / "auto-memory"
    shutil.copytree(FIXTURE, auto)

    result = subprocess.run(
        [str(SCRIPT), "--batch"],
        env={
            "AUTO_MEMORY_DIR": str(auto),
            "MEMORY_VAULT_DIR": str(vault),
            "PATH": os.environ["PATH"],
        },
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    memory_subj_dir = vault / "10-projects" / "memory" / ".memory"
    assert memory_subj_dir.is_dir()
    files = list(memory_subj_dir.glob("*.md"))
    assert any("memory-plugin-vault-is-store" in f.name for f in files)


def test_idempotent_on_re_run(tmp_path):
    """Re-running with --batch surfaces collisions but exits cleanly. The
    'already migrated' notice goes to stderr; assert against combined output."""
    vault = _make_vault(tmp_path)
    (vault / ".memory").mkdir(parents=True)
    auto = tmp_path / "auto-memory"
    shutil.copytree(FIXTURE, auto)

    env = {
        "AUTO_MEMORY_DIR": str(auto),
        "MEMORY_VAULT_DIR": str(vault),
        "PATH": os.environ["PATH"],
    }
    first = subprocess.run([str(SCRIPT), "--batch"], env=env, capture_output=True, text=True, timeout=30)
    assert first.returncode == 0

    second = subprocess.run([str(SCRIPT), "--batch"], env=env, capture_output=True, text=True, timeout=30)
    assert second.returncode == 0
    combined = second.stdout + second.stderr
    assert "already migrated" in combined.lower() or "collision" in combined.lower()
