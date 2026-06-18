"""memory CLI: thin argparse surface over memory_writer/memory_reader/index.

Subcommands:
    memory write --type T --name N --subject S --description D    # body from stdin
    memory list  [--type T] [--subject S]
    memory get   --name N --type T
    memory rebuild-index

Invoked via bin/memory, which execs the plugin .venv python on this file.
bin/memory passes the file path directly (not as a package), so we put the
sibling lib/ directory on sys.path before importing the in-tree modules.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sibling modules (memory_writer, memory_reader, index, providers)
# importable when this file is invoked as a script (lib/cli.py).
sys.path.insert(0, str(Path(__file__).parent))

import index  # noqa: E402
import memory_reader  # noqa: E402
import memory_writer  # noqa: E402
from lock import MemoryLockTimeoutError  # noqa: E402
from providers.base import (  # noqa: E402
    MemoryAmbiguousSubjectError,
    MemoryCollisionError,
    MemorySubjectNotFoundError,
)


from config import resolve_vault_root as _resolve_vault_root  # noqa: E402

import os  # noqa: E402


def _memory_root() -> Path:
    return Path(os.environ.get("MEMORY_ROOT", str(Path(__file__).resolve().parent.parent)))


def _now_stamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def cmd_note(args: argparse.Namespace) -> int:
    from session_notes import append_note  # noqa: E402

    append_note(args.text, root=_memory_root(), stamp=_now_stamp())
    print("noted")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    import shlex  # noqa: E402
    import subprocess  # noqa: E402

    from session_notes import clear_notes, read_notes  # noqa: E402
    from session_recorder import record as do_record  # noqa: E402
    from transcript import digest  # noqa: E402

    root = _memory_root()
    template_path = os.environ.get(
        "MEMORY_RECORD_TEMPLATE",
        str(root / "templates" / "session-record.md"),
    )
    template = Path(template_path).read_text(encoding="utf-8")
    transcript_text = digest(args.transcript, max_chars=24_000)
    notes = read_notes(root)

    runner_cmd = os.environ.get("MEMORY_RECORD_RUNNER")  # test/override hook

    def runner(prompt: str) -> str:
        if runner_cmd:  # fake/override runner for tests or alternate models
            cp = subprocess.run(
                shlex.split(runner_cmd),
                input=prompt,
                capture_output=True,
                text=True,
            )
            return cp.stdout
        # default: headless claude -p; loop-guard prevents re-trigger
        env = dict(os.environ)
        env["MEMORY_RECORDING"] = "1"
        cp = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
        return cp.stdout

    def writer(record_text: str) -> None:
        subprocess.run(
            [
                str(root / "bin" / "memory"),
                "write",
                "--type",
                "project",
                "--subject",
                "session-records",
                "--name",
                f"{_now_stamp()}-session-record",
                "--description",
                "informed session record",
            ],
            input=record_text,
            text=True,
            check=True,
        )

    result = do_record(transcript_text, notes, template, runner=runner, writer=writer)
    if result.written:
        clear_notes(root)
        print("recorded")
    else:
        print("nothing worth recording")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    body = sys.stdin.read()
    try:
        path = memory_writer.write(
            name=args.name,
            description=args.description,
            type=args.type,
            subject=args.subject,
            body=body,
        )
    except (
        ValueError,
        MemoryCollisionError,
        MemoryAmbiguousSubjectError,
        MemorySubjectNotFoundError,
        MemoryLockTimeoutError,
    ) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(path)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    entries = memory_reader.list(type=args.type, subject=args.subject)
    for entry in entries:
        print(f"{entry.type}:{entry.subject}:{entry.name} \u2014 {entry.description}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    entry = memory_reader.get(args.name, args.type)
    if entry is None:
        print("not found", file=sys.stderr)
        return 1
    sys.stdout.write(entry.to_markdown())
    return 0


def cmd_rebuild_index(args: argparse.Namespace) -> int:
    vault_root = _resolve_vault_root()
    try:
        count = index.rebuild_from_scan(vault_root)
    except MemoryLockTimeoutError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(count)
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    out = memory_reader.brief()
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def cmd_resolve_scope(args: argparse.Namespace) -> int:
    entries = memory_reader.resolve_scope(args.subject)
    for entry in entries:
        print(f"{entry.type}:{entry.subject}:{entry.name} — {entry.description}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory",
        description="Durable agent-observation memory CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_write = sub.add_parser("write", help="Write a memory entry (body from stdin).")
    p_write.add_argument("--type", required=True)
    p_write.add_argument("--name", required=True)
    p_write.add_argument("--subject", required=True)
    p_write.add_argument("--description", required=True)
    p_write.set_defaults(func=cmd_write)

    p_list = sub.add_parser("list", help="List memory entries from MEMORY.md.")
    p_list.add_argument("--type", default=None)
    p_list.add_argument("--subject", default=None)
    p_list.set_defaults(func=cmd_list)

    p_get = sub.add_parser("get", help="Fetch one entry by (name, type).")
    p_get.add_argument("--name", required=True)
    p_get.add_argument("--type", required=True)
    p_get.set_defaults(func=cmd_get)

    p_rebuild = sub.add_parser(
        "rebuild-index",
        help="Rescan the vault and rewrite MEMORY.md from frontmatter.",
    )
    p_rebuild.set_defaults(func=cmd_rebuild_index)

    p_brief = sub.add_parser("brief", help="Emit memory's session-start brief")
    p_brief.set_defaults(func=cmd_brief)

    p_scope = sub.add_parser("resolve-scope", help="List entries in scope for a subject")
    p_scope.add_argument("subject")
    p_scope.set_defaults(func=cmd_resolve_scope)

    p_note = sub.add_parser("note", help="Append a lightweight in-session note.")
    p_note.add_argument("text")
    p_note.set_defaults(func=cmd_note)

    p_record = sub.add_parser(
        "record", help="Compose and write an informed session record."
    )
    p_record.add_argument("--transcript", required=True)
    p_record.set_defaults(func=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
