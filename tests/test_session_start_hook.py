"""Tests for the SessionStart hook wrapper script."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path


HOOK = Path(__file__).parent.parent / "hooks" / "session-start.sh"
FAKE_PLUGIN_NO_BIN = Path(__file__).parent / "fixtures" / "fake_plugin_no_bin"


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], **env_extra}
    return subprocess.run(
        [str(HOOK)], env=env, capture_output=True, text=True, timeout=20,
    )


def test_hook_returns_valid_json_envelope(tmp_path):
    root = tmp_path / "vault"
    (root / ".memory").mkdir(parents=True)
    md = (
        "---\nname: hook-test\ndescription: hello\ntype: user\nsubject: user\n---\nbody\n"
    )
    (root / ".memory" / f"{date.today().isoformat()}-hook-test.md").write_text(md)

    result = _run({"MEMORY_VAULT_DIR": str(root)})

    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert "hookSpecificOutput" in envelope
    assert envelope["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "hook-test" in envelope["hookSpecificOutput"]["additionalContext"]


def test_hook_disable_flag_emits_empty_context(tmp_path):
    result = _run({"MEMORY_VAULT_DIR": str(tmp_path), "MEMORY_SESSION_SUMMARY": "0"})

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["hookSpecificOutput"]["additionalContext"] == ""


def test_hook_missing_bin_falls_through_to_empty(tmp_path):
    """If MEMORY_ROOT points at a plugin dir with no bin/memory, the hook
    emits empty context and exits 0 (omit_section)."""
    result = _run({
        "MEMORY_VAULT_DIR": str(tmp_path),
        "MEMORY_ROOT": str(FAKE_PLUGIN_NO_BIN),
    })

    assert result.returncode == 0
    envelope = json.loads(result.stdout)
    assert envelope["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert envelope["hookSpecificOutput"]["additionalContext"] == ""
