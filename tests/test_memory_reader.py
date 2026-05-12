"""Tests for lib/memory_reader.py: list/get against an indexed vault."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import index
import memory_reader


def _write_entry_file(
    vault: Path,
    rel_path: str,
    name: str,
    description: str,
    type: str,
    subject: str,
    body: str,
) -> None:
    """Write a memory entry markdown file with 4-field YAML frontmatter + body."""
    target = vault / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    fm = (
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"type: {type}\n"
        f"subject: {subject}\n"
        "---\n"
    )
    target.write_text(fm + body, encoding="utf-8")


@pytest.fixture
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point MEMORY_VAULT_DIR at tmp_path and populate a small indexed corpus."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))

    rows = [
        (
            "users/alice/profile.md",
            "alice",
            "primary user",
            "user",
            "alice",
            "alice body\n",
        ),
        (
            "users/alice/pref.md",
            "alice-pref",
            "alice preferences",
            "feedback",
            "alice",
            "alice prefers concise\n",
        ),
        (
            "projects/memory/plan.md",
            "plan",
            "memory v0 plan",
            "project",
            "memory",
            "plan body\n",
        ),
    ]
    for rel, name, desc, type_, subject, body in rows:
        _write_entry_file(
            tmp_path,
            rel_path=rel,
            name=name,
            description=desc,
            type=type_,
            subject=subject,
            body=body,
        )
        index.append(
            tmp_path,
            name=name,
            type=type_,
            subject=subject,
            path=rel,
            description=desc,
        )
    return tmp_path


def test_list_returns_all_entries(vault: Path) -> None:
    entries = memory_reader.list()
    assert len(entries) == 3
    names = sorted(e.name for e in entries)
    assert names == ["alice", "alice-pref", "plan"]


def test_list_filter_by_type(vault: Path) -> None:
    entries = memory_reader.list(type="user")
    assert len(entries) == 1
    assert entries[0].name == "alice"
    assert entries[0].type == "user"


def test_list_filter_by_subject(vault: Path) -> None:
    entries = memory_reader.list(subject="alice")
    assert len(entries) == 2
    assert sorted(e.name for e in entries) == ["alice", "alice-pref"]
    assert all(e.subject == "alice" for e in entries)


def test_list_compound_filter(vault: Path) -> None:
    entries = memory_reader.list(type="feedback", subject="alice")
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "alice-pref"
    assert e.type == "feedback"
    assert e.subject == "alice"


def test_get_returns_entry(vault: Path) -> None:
    e = memory_reader.get("alice", "user")
    assert e is not None
    assert e.name == "alice"
    assert e.description == "primary user"
    assert e.type == "user"
    assert e.subject == "alice"
    assert e.body == "alice body\n"


def test_get_unknown_returns_none(vault: Path) -> None:
    assert memory_reader.get("nope", "user") is None
    assert memory_reader.get("alice", "reference") is None


def test_same_name_different_types_coexist(vault: Path) -> None:
    # Add a 4th entry sharing the name "alice" but with type=reference.
    rel = "references/alice-ref.md"
    _write_entry_file(
        vault,
        rel_path=rel,
        name="alice",
        description="alice reference",
        type="reference",
        subject="alice",
        body="ref body\n",
    )
    index.append(
        vault,
        name="alice",
        type="reference",
        subject="alice",
        path=rel,
        description="alice reference",
    )

    e_user = memory_reader.get("alice", "user")
    e_ref = memory_reader.get("alice", "reference")
    assert e_user is not None
    assert e_ref is not None
    assert e_user.description == "primary user"
    assert e_ref.description == "alice reference"
    assert e_user.body == "alice body\n"
    assert e_ref.body == "ref body\n"


def test_missing_memory_md_triggers_rebuild(
    vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Remove MEMORY.md so list() must fall back to rebuild_from_scan.
    (vault / "MEMORY.md").unlink()
    assert not (vault / "MEMORY.md").exists()

    with caplog.at_level(logging.WARNING, logger="memory_reader"):
        entries = memory_reader.list()

    # Rebuild succeeded and re-indexed all 3 entries.
    assert len(entries) == 3
    assert (vault / "MEMORY.md").exists()
    # Warning was emitted about the missing index.
    assert any(
        "MEMORY.md missing" in rec.getMessage() for rec in caplog.records
    ), f"expected missing-MEMORY.md warning; got {[r.getMessage() for r in caplog.records]}"


def test_malformed_bullet_is_skipped(vault: Path) -> None:
    # Inject a malformed line into MEMORY.md; index.read should skip it,
    # list() should still return all valid entries.
    idx = vault / "MEMORY.md"
    text = idx.read_text(encoding="utf-8")
    idx.write_text(text + "- [[broken bullet without proper format\n", encoding="utf-8")

    entries = memory_reader.list()
    assert len(entries) == 3
    assert sorted(e.name for e in entries) == ["alice", "alice-pref", "plan"]
