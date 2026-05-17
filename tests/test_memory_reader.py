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


def test_list_rebuilds_when_memory_md_exists_but_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per the module docstring, list() falls back to rebuild when the
    index is missing or empty. A header-only MEMORY.md must trigger the
    rebuild — the previous .exists() guard skipped this case."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    # Create an entry on disk but NO matching index entry.
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    (tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-orphan.md").write_text(
        "---\n"
        "name: orphan\n"
        "description: only on disk\n"
        "type: project\n"
        "subject: foo\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    # Header-only MEMORY.md — exists, but has no bullets.
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\nAuto-maintained.\n\n", encoding="utf-8"
    )

    result = memory_reader.list()
    assert [e.name for e in result] == ["orphan"]


def test_get_rebuilds_when_memory_md_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per the module docstring, get() falls back to rebuild on
    missing/empty index. Previously get() returned None unconditionally."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    (tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-needle.md").write_text(
        "---\n"
        "name: needle\n"
        "description: findable via rebuild\n"
        "type: project\n"
        "subject: foo\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    # No MEMORY.md at all.
    assert not (tmp_path / "MEMORY.md").exists()

    entry = memory_reader.get("needle", "project")
    assert entry is not None
    assert entry.name == "needle"


def test_get_does_not_rebuild_on_real_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the index has entries but doesn't contain the requested
    (name, type), that's a real miss — don't waste a rebuild scan."""
    import unittest.mock as mock
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    # Seed the index with an unrelated entry so it's non-empty.
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    real_path = tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-other.md"
    real_path.write_text(
        "---\nname: other\ndescription: d\ntype: project\nsubject: foo\n---\nb\n",
        encoding="utf-8",
    )
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\n"
        "- [[10-projects/foo/project/2026-05-12-other.md|other]] · "
        "type:project subject:foo · d\n",
        encoding="utf-8",
    )

    with mock.patch("index.rebuild_from_scan") as rebuild:
        entry = memory_reader.get("missing", "project")
    assert entry is None
    rebuild.assert_not_called()


def test_parse_entry_file_handles_dashes_in_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Description values that contain '---' must not confuse the
    frontmatter parser. Regression for greptile P1: the previous
    split-on-substring parser fired inside the frontmatter when a field
    value contained '---', silently dropping the entry on read."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    entry_dir = tmp_path / "10-projects" / "foo" / "project"
    entry_dir.mkdir(parents=True)
    # yaml.safe_dump produces 'description: setup --- teardown' (unquoted,
    # single line). Old parser saw '---' as a delimiter and split mid-yaml.
    entry_file = entry_dir / "2026-05-12-dashes.md"
    entry_file.write_text(
        "---\n"
        "name: dashes\n"
        "description: setup --- teardown\n"
        "type: project\n"
        "subject: foo\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\n"
        f"- [[{entry_file.relative_to(tmp_path)}|dashes]] · "
        f"type:project subject:foo · setup --- teardown\n",
        encoding="utf-8",
    )

    entry = memory_reader.get("dashes", "project")
    assert entry is not None
    assert entry.name == "dashes"
    assert entry.description == "setup --- teardown"


def test_get_skips_entry_with_non_utf8_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A memory file whose body contains non-UTF-8 bytes must not crash
    list()/get(). Treat as malformed and skip — matches the existing
    OSError handling semantics."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    entry_dir = tmp_path / "10-projects" / "foo" / "project"
    entry_dir.mkdir(parents=True)
    bad = entry_dir / "2026-05-12-bad.md"
    bad.write_bytes(
        b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
        + b"\xff\xff non-utf8 body"
    )
    # Manually populate MEMORY.md so reader.get() finds the index entry
    # and then tries to read the file (where the crash used to happen).
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\n"
        f"- [[{bad.relative_to(tmp_path)}|bad]] · type:project subject:foo · d\n",
        encoding="utf-8",
    )

    # Before the fix this raised UnicodeDecodeError from read_text.
    assert memory_reader.get("bad", "project") is None


def test_list_skips_entries_with_non_utf8_bodies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One malformed file must not poison the whole list() result."""
    monkeypatch.setenv("MEMORY_VAULT_DIR", str(tmp_path))
    entry_dir = tmp_path / "10-projects" / "foo" / "project"
    entry_dir.mkdir(parents=True)
    good = entry_dir / "2026-05-12-good.md"
    good.write_text(
        "---\nname: good\ndescription: d\ntype: project\nsubject: foo\n---\nbody\n",
        encoding="utf-8",
    )
    bad = entry_dir / "2026-05-12-bad.md"
    bad.write_bytes(
        b"---\nname: bad\ndescription: d\ntype: project\nsubject: foo\n---\n"
        + b"\xff\xff non-utf8"
    )
    (tmp_path / "MEMORY.md").write_text(
        "# MEMORY\n\n"
        f"- [[{good.relative_to(tmp_path)}|good]] · type:project subject:foo · d\n"
        f"- [[{bad.relative_to(tmp_path)}|bad]] · type:project subject:foo · d\n",
        encoding="utf-8",
    )

    names = [e.name for e in memory_reader.list()]
    assert names == ["good"]
