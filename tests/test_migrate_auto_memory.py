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


def test_body_with_inner_horizontal_rule_is_preserved(tmp_path):
    """Body extraction must not strip markdown horizontal rules (---) inside bodies."""
    vault = _make_vault(tmp_path)
    (vault / ".memory").mkdir(parents=True)
    auto = tmp_path / "auto-memory"
    auto_inner = auto / "-fixture/memory"
    auto_inner.mkdir(parents=True)
    (auto_inner / "feedback_with_hr.md").write_text(
        "---\n"
        "name: with-hr\n"
        "description: has a horizontal rule\n"
        "metadata:\n"
        "  type: feedback\n"
        "---\n"
        "First paragraph.\n"
        "\n"
        "---\n"
        "\n"
        "Second paragraph after horizontal rule.\n"
    )

    import os
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

    # Locate the migrated entry and confirm the inner --- survives.
    user_memory = vault / ".memory"
    files = list(user_memory.glob("*-with-hr.md"))
    assert len(files) == 1, f"expected 1 migrated file, found: {list(user_memory.iterdir())}"
    body = files[0].read_text()
    assert "First paragraph." in body
    assert "Second paragraph after horizontal rule." in body
    assert "\n---\n" in body, "horizontal rule (---) was stripped from body"
