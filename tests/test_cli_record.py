# tests/test_cli_record.py
import json
import os
import subprocess
from pathlib import Path

MEM = Path(__file__).resolve().parent.parent
CLI = MEM / "bin" / "memory"


def _env(tmp_path):
    env = dict(os.environ)
    env["MEMORY_VAULT_DIR"] = str(tmp_path / "vault")
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)
    return env


# bin/memory hardcodes MEMORY_ROOT to its own install location (so it can find
# the .venv and lib/cli.py), so notes always land in the real <root>/var/
# pending-notes.md — a pre-set MEMORY_ROOT env var is clobbered by the launcher.
# To keep the suite from polluting the dev tree, snapshot that file and restore
# it afterward. (A proper data-root override is a separate enhancement that
# would touch the production launcher; out of scope for this test-only fix.)
NOTES_FILE = MEM / "var" / "pending-notes.md"


def _restore_notes(prev):
    """Restore the real pending-notes file to its pre-test state."""
    if prev is None:
        if NOTES_FILE.exists():
            NOTES_FILE.unlink()
        # remove the var/ dir only if this test created it and it is now empty
        var_dir = NOTES_FILE.parent
        if var_dir.is_dir() and not any(var_dir.iterdir()):
            var_dir.rmdir()
    else:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        NOTES_FILE.write_text(prev, encoding="utf-8")


def test_note_appends(tmp_path):
    env = _env(tmp_path)
    prev = NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else None
    try:
        r = subprocess.run([str(CLI), "note", "ClientA: drafted spec"],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        # note landed (append, non-crashing) — exercises the real bin/memory path
        assert NOTES_FILE.is_file()
        assert "ClientA: drafted spec" in NOTES_FILE.read_text(encoding="utf-8")
    finally:
        _restore_notes(prev)


def test_record_declines_gracefully_with_fake_runner(tmp_path):
    env = _env(tmp_path)
    env["MEMORY_RECORD_RUNNER"] = "echo <<NOTHING-WORTH-RECORDING>>"  # fake runner
    t = tmp_path / "t.jsonl"
    line = json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
    t.write_text(line, encoding="utf-8")
    # fake runner returns the skip sentinel → record() declines, writer never
    # runs, no real claude is invoked and nothing is written to the vault.
    r = subprocess.run([str(CLI), "record", "--transcript", str(t)],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "nothing worth recording" in r.stdout.lower()


def test_record_preserves_notes_on_vault_write_failure(tmp_path):
    """Fail-safe: when the vault write fails, notes are preserved and no traceback escapes."""
    import json as _json
    env = _env(tmp_path)
    # Real content runner so record() proceeds past the skip check
    env["MEMORY_RECORD_RUNNER"] = "echo # Fake record content"
    # Break the vault by making MEMORY_VAULT_DIR a file (write will fail)
    bad_vault = tmp_path / "not_a_dir.txt"
    bad_vault.write_text("not a vault", encoding="utf-8")
    env["MEMORY_VAULT_DIR"] = str(bad_vault)

    t = tmp_path / "t.jsonl"
    t.write_text(
        _json.dumps({"type": "user", "message": {"role": "user", "content": "do work"}}) + "\n",
        encoding="utf-8",
    )

    prev = NOTES_FILE.read_text(encoding="utf-8") if NOTES_FILE.exists() else None
    NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTES_FILE.write_text("- [2026-01-01T00:00] existing note\n", encoding="utf-8")
    try:
        r = subprocess.run(
            [str(CLI), "record", "--transcript", str(t)],
            env=env, capture_output=True, text=True,
        )
        assert r.returncode == 0, f"non-zero exit: {r.returncode}\nstderr: {r.stderr}"
        assert "Traceback" not in r.stderr, f"traceback escaped: {r.stderr}"
        assert NOTES_FILE.exists() and "existing note" in NOTES_FILE.read_text(encoding="utf-8"), (
            "notes were cleared on vault write failure"
        )
    finally:
        _restore_notes(prev)
