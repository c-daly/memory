# tests/test_transcript.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from transcript import digest  # noqa: E402


def _write_jsonl(p: Path, rows: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_digest_extracts_user_and_assistant_text(tmp_path):
    t = tmp_path / "t.jsonl"
    _write_jsonl(t, [
        {"type": "user", "message": {"role": "user", "content": "do X for ClientA"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "did X"}},
        {"type": "system", "message": {"role": "system", "content": "ignore me"}},
    ])
    out = digest(t, max_chars=10_000)
    assert "do X for ClientA" in out
    assert "did X" in out
    assert "ignore me" not in out  # system rows excluded


def test_digest_is_bounded_and_keeps_the_tail(tmp_path):
    t = tmp_path / "t.jsonl"
    # Two-region fixture: 60 OLD rows then 60 NEW rows.
    # max_chars=300 is sized to hold only the NEW tail.
    old_rows = [{"type": "user", "message": {"role": "user", "content": "OLD_MARKER " * 10}}
                for _ in range(60)]
    new_rows = [{"type": "user", "message": {"role": "user", "content": "NEW_MARKER " * 10}}
                for _ in range(60)]
    _write_jsonl(t, old_rows + new_rows)
    out = digest(t, max_chars=300)
    assert len(out) <= 300
    assert "NEW_MARKER" in out        # tail is preserved
    assert "OLD_MARKER" not in out    # head is truncated


def test_digest_missing_file_returns_empty(tmp_path):
    assert digest(tmp_path / "nope.jsonl", max_chars=100) == ""
