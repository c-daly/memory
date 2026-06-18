# tests/test_session_notes.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from session_notes import append_note, read_notes, clear_notes, notes_path  # noqa: E402


def test_append_then_read(tmp_path):
    append_note("decided to use X", root=tmp_path, stamp="2026-06-04T10:00")
    append_note("ClientA invoice prep", root=tmp_path, stamp="2026-06-04T10:05")
    out = read_notes(root=tmp_path)
    assert "decided to use X" in out
    assert "ClientA invoice prep" in out
    assert "2026-06-04T10:00" in out  # timestamped


def test_read_empty_when_no_notes(tmp_path):
    assert read_notes(root=tmp_path) == ""


def test_clear_removes_pending(tmp_path):
    append_note("x", root=tmp_path, stamp="2026-06-04T10:00")
    clear_notes(root=tmp_path)
    assert read_notes(root=tmp_path) == ""
    assert not notes_path(tmp_path).exists()
