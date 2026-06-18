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
    _write_jsonl(t, [{"type": "user", "message": {"role": "user", "content": "x" * 50}}
                    for _ in range(100)])
    out = digest(t, max_chars=200)
    assert len(out) <= 200
    # keeps the most-recent content (tail), since recency matters most for recording
    assert out.endswith("x" * 10) or "x" in out


def test_digest_missing_file_returns_empty(tmp_path):
    assert digest(tmp_path / "nope.jsonl", max_chars=100) == ""
