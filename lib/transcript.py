# lib/transcript.py
"""Read a Claude Code transcript (.jsonl) into a bounded plain-text digest.

The transcript is one JSON object per line. We keep only user/assistant text,
join it chronologically, and trim to the tail (most recent) within max_chars,
because the recorder cares most about what happened recently.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Union

_KEEP_ROLES = {"user", "assistant"}


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def digest(transcript_path: Union[str, Path], max_chars: int) -> str:
    p = Path(transcript_path)
    if not p.is_file():
        return ""
    lines: list[str] = []
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg = row.get("message") or {}
        role = msg.get("role") or row.get("type")
        if role not in _KEEP_ROLES:
            continue
        text = _content_text(msg.get("content", "")).strip()
        if text:
            lines.append(f"{role}: {text}")
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[-max_chars:]
    return out
