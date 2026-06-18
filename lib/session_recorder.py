"""Compose an informed session record and persist it.

The runner (default: headless `claude -p`) is the informed author — it receives
the transcript digest + in-session notes + the template and returns either a
filled record or SKIP_SENTINEL when nothing is worth recording. runner and
writer are injected so the logic is unit-testable without a model or the vault.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

SKIP_SENTINEL = "<<NOTHING-WORTH-RECORDING>>"

_PROMPT = """You are an informed recorder writing a durable record of a work session
for the user to look back on months later (e.g. to reconstruct an invoice). You were
present for this session. Write a faithful, concise record using ONLY the template
below. Fill every placeholder. Attribute to the project/client and date. Capture what
was actually done and learned — not narration of your own process.

If there is genuinely nothing worth recording, reply with EXACTLY: {sentinel}

TEMPLATE:
{template}

IN-SESSION NOTES (anchors the user/agent jotted while working):
{notes}

SESSION TRANSCRIPT (most recent activity):
{transcript}
"""


@dataclass(frozen=True)
class RecordResult:
    written: bool
    record_text: str = ""


def build_prompt(transcript: str, notes: str, template: str) -> str:
    return _PROMPT.format(sentinel=SKIP_SENTINEL, template=template,
                          notes=notes or "(none)", transcript=transcript or "(none)")


def record(
    transcript: str,
    notes: str,
    template: str,
    runner: Callable[[str], str],
    writer: Callable[[str], None],
) -> RecordResult:
    prompt = build_prompt(transcript, notes, template)
    out = (runner(prompt) or "").strip()
    if not out or out == SKIP_SENTINEL:
        return RecordResult(written=False)
    writer(out)
    return RecordResult(written=True, record_text=out)
