# tests/test_session_recorder.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from session_recorder import build_prompt, record, SKIP_SENTINEL  # noqa: E402


def test_build_prompt_includes_transcript_notes_and_template():
    prompt = build_prompt(transcript="user: do X", notes="- did Y", template="TPL:{{summary}}")
    assert "do X" in prompt
    assert "did Y" in prompt
    assert "TPL:{{summary}}" in prompt
    assert SKIP_SENTINEL in prompt  # recorder is told how to decline


def test_record_runs_then_writes():
    captured = {}

    def fake_runner(prompt: str) -> str:
        captured["prompt"] = prompt
        return "# 2026-06-04 — agent-swarm\n**Summary:** did X"

    def fake_writer(record_text: str) -> None:
        captured["record"] = record_text

    result = record(transcript="user: do X", notes="invoiced ClientA 2h", template="t",
                    runner=fake_runner, writer=fake_writer)
    assert result.written is True
    assert "did X" in captured["record"]
    # record_text on the result is exactly the text handed to the writer
    assert result.record_text == captured["record"]
    # non-empty notes flow through record() -> build_prompt() into the runner prompt
    assert "invoiced ClientA 2h" in captured["prompt"]


def test_record_skips_write_when_runner_declines():
    def fake_runner(prompt: str) -> str:
        return SKIP_SENTINEL

    def fake_writer(record_text: str) -> None:
        raise AssertionError("writer must not be called when recorder declines")

    result = record(transcript="trivial", notes="", template="t",
                    runner=fake_runner, writer=fake_writer)
    assert result.written is False


def test_record_skips_write_on_empty_runner_output():
    result = record(transcript="x", notes="", template="t",
                    runner=lambda p: "   ", writer=lambda r: (_ for _ in ()).throw(AssertionError()))
    assert result.written is False


def test_build_prompt_survives_single_brace_template():
    """User templates with single-brace placeholders must not raise KeyError."""
    template = "Record: {client} on {date}"
    prompt = build_prompt(transcript="user: did work", notes="- note", template=template)
    # The raw single-brace content survives in the output unchanged
    assert "{client}" in prompt
    assert "{date}" in prompt
    # Core prompt structure is still intact
    assert SKIP_SENTINEL in prompt
