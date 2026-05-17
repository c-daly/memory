"""Tests for lib/index.py: MEMORY.md read/append/lookup/rebuild."""
from __future__ import annotations

from pathlib import Path
import threading

import index
from lock import memory_lock


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    assert index.read(tmp_path) == []


def test_append_creates_index_with_header_and_bullet(tmp_path: Path) -> None:
    index.append(
        tmp_path,
        name="alice",
        type="user",
        subject="alice",
        path="users/alice/profile.md",
        description="primary user",
    )
    idx_file = tmp_path / "MEMORY.md"
    assert idx_file.exists()
    text = idx_file.read_text(encoding="utf-8")
    assert text.startswith("# MEMORY\n")
    assert "Auto-maintained by memory_writer." in text

    entries = index.read(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e.name == "alice"
    assert e.type == "user"
    assert e.subject == "alice"
    assert e.path == "users/alice/profile.md"
    assert e.description == "primary user"


def test_multiple_appends_preserve_order(tmp_path: Path) -> None:
    rows = [
        ("alice", "user", "alice", "users/alice.md", "first"),
        ("bob-pref", "feedback", "bob", "users/bob.md", "second"),
        ("plan", "project", "memory", "projects/memory/plan.md", "third"),
    ]
    for r in rows:
        index.append(tmp_path, name=r[0], type=r[1], subject=r[2], path=r[3], description=r[4])

    entries = index.read(tmp_path)
    assert len(entries) == 3
    assert [e.name for e in entries] == ["alice", "bob-pref", "plan"]
    assert [e.description for e in entries] == ["first", "second", "third"]


def test_lookup_hit_and_miss(tmp_path: Path) -> None:
    index.append(
        tmp_path,
        name="alice",
        type="user",
        subject="alice",
        path="users/alice.md",
        description="primary user",
    )
    assert index.lookup(tmp_path, "alice", "user") == "users/alice.md"
    assert index.lookup(tmp_path, "alice", "feedback") is None
    assert index.lookup(tmp_path, "unknown", "user") is None


def test_lookup_subject_hit_and_miss(tmp_path: Path) -> None:
    index.append(
        tmp_path,
        name="plan",
        type="project",
        subject="memory",
        path="projects/memory/plan.md",
        description="the plan",
    )
    assert index.lookup_subject(tmp_path, "memory") == "projects/memory"
    assert index.lookup_subject(tmp_path, "nope") is None


def _write_md(p: Path, frontmatter: dict | None, body: str = "body\n") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        p.write_text(body, encoding="utf-8")
        return
    lines = ["---"]
    for k, v in frontmatter.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append(body)
    p.write_text("\n".join(lines), encoding="utf-8")


def test_rebuild_from_scan(tmp_path: Path) -> None:
    _write_md(
        tmp_path / "users" / "alice.md",
        {"name": "alice", "description": "primary", "type": "user", "subject": "alice"},
    )
    _write_md(
        tmp_path / "projects" / "memory" / "plan.md",
        {
            "name": "plan",
            "description": "the plan",
            "type": "project",
            "subject": "memory",
        },
    )
    _write_md(
        tmp_path / "broken1.md",
        {"name": "x", "description": "y", "type": "user"},
    )
    _write_md(tmp_path / "plain.md", None, body="just a markdown file\n")
    (tmp_path / "notes.txt").write_text("not markdown", encoding="utf-8")

    count = index.rebuild_from_scan(tmp_path)
    assert count == 2

    entries = index.read(tmp_path)
    assert len(entries) == 2
    by_name = {e.name: e for e in entries}
    assert set(by_name) == {"alice", "plan"}
    assert by_name["alice"].path == "users/alice.md"
    assert by_name["plan"].path == "projects/memory/plan.md"
    assert by_name["plan"].subject == "memory"

    text = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert text.startswith("# MEMORY\n")


def test_rebuild_from_scan_waits_for_provider_root_lock(tmp_path: Path) -> None:
    _write_md(
        tmp_path / "users" / "alice.md",
        {"name": "alice", "description": "primary", "type": "user", "subject": "alice"},
    )
    finished = threading.Event()
    result: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            result.append(index.rebuild_from_scan(tmp_path))
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            finished.set()

    with memory_lock(tmp_path, context="test-hold"):
        thread = threading.Thread(target=worker)
        thread.start()
        assert not finished.wait(0.1)

    assert finished.wait(2.0)
    thread.join()
    assert errors == []
    assert result == [1]


def test_rebuild_from_scan_skips_body_bytes(tmp_path: Path) -> None:
    """Bodies aren't needed to (re)build MEMORY.md — only frontmatter is.

    Behavioral guard: write a file whose body contains non-UTF-8 bytes.
    A head-only reader stops at the closing '---' and never decodes the
    body, so the file is indexed normally. A full-file reader hits
    UnicodeDecodeError on the body and the file is silently skipped
    (resulting in count == 0 here).
    """
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    bad_file = tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-bad.md"
    frontmatter = (
        "---\n"
        "name: bad\n"
        "description: body has bad bytes\n"
        "type: project\n"
        "subject: foo\n"
        "---\n"
    ).encode("utf-8")
    # 0xff isn't valid UTF-8 anywhere; reading past the frontmatter
    # would raise UnicodeDecodeError under encoding="utf-8".
    bad_file.write_bytes(frontmatter + b"\xff\xff body bytes that won\'t decode")

    count = index.rebuild_from_scan(tmp_path)
    assert count == 1


def test_read_frontmatter_only_handles_crlf(tmp_path: Path) -> None:
    """Windows-style CRLF line endings must not break delimiter detection.

    Previously rstrip('\\n') left a trailing '\\r' on the '---' lines,
    causing the equality check to fail and the file to be silently
    skipped by rebuild_from_scan.
    """
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    crlf_file = tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-crlf.md"
    crlf_file.write_bytes(
        b"---\r\n"
        b"name: crlf\r\n"
        b"description: windows line endings\r\n"
        b"type: project\r\n"
        b"subject: foo\r\n"
        b"---\r\n"
        b"body\r\n"
    )

    count = index.rebuild_from_scan(tmp_path)
    assert count == 1
    parsed = index.read(tmp_path)
    assert parsed[0].name == "crlf"


def test_read_returns_empty_on_non_utf8_memory_md(tmp_path: Path) -> None:
    """A corrupt MEMORY.md (non-UTF-8 bytes from a partial write or
    hand-edit) must not crash callers — return [] so the reader's
    missing-or-empty fallback drives a rebuild."""
    (tmp_path / "MEMORY.md").write_bytes(
        b"# MEMORY\n\n- [[10-projects/foo/project/2026-05-12-x.md|x]] "
        + b"\xb7 type:project subject:foo \xb7 \xff\xff bad\n"
    )
    # Before the fix this raised UnicodeDecodeError during the for-loop iteration.
    assert index.read(tmp_path) == []


def test_append_recovers_from_non_utf8_memory_md(tmp_path: Path) -> None:
    """If MEMORY.md is corrupt at append-time, recover by rebuilding from
    disk instead of crashing. The entry file is already on disk by the
    time append() is called (writer order is put-then-append), so the
    rebuild picks it up and the resulting MEMORY.md is consistent."""
    # Pre-existing entry on disk
    (tmp_path / "10-projects" / "foo" / "project").mkdir(parents=True)
    (tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-other.md").write_text(
        "---\nname: other\ndescription: d\ntype: project\nsubject: foo\n---\nb\n",
        encoding="utf-8",
    )
    # New entry that's about to be appended (simulate the writer order:
    # provider.put has already created this file).
    (tmp_path / "10-projects" / "foo" / "project" / "2026-05-12-new.md").write_text(
        "---\nname: new\ndescription: d\ntype: project\nsubject: foo\n---\nb\n",
        encoding="utf-8",
    )
    # Corrupt MEMORY.md
    (tmp_path / "MEMORY.md").write_bytes(b"corrupt\xff\xff\xff bytes")

    # Before the fix this raised UnicodeDecodeError out of append().
    index.append(
        tmp_path,
        name="new",
        type="project",
        subject="foo",
        path="10-projects/foo/project/2026-05-12-new.md",
        description="d",
    )

    # Post-rebuild MEMORY.md should be valid and contain BOTH entries.
    entries = index.read(tmp_path)
    names = sorted(e.name for e in entries)
    assert names == ["new", "other"]
