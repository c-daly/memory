"""Tests for scripts/check-memory-path-usage.sh."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent.parent / "scripts" / "check-memory-path-usage.sh"
FIXTURE = Path(__file__).parent / "fixtures" / "cc_session_sample.jsonl"


def test_aggregator_counts_auto_memory_and_plugin_writes(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "session.jsonl").write_text(FIXTURE.read_text())

    result = subprocess.run(
        [str(SCRIPT)],
        env={"CC_SESSION_DIR": str(log_dir), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "auto-memory: 2" in result.stdout
    assert "plugin: 2" in result.stdout
