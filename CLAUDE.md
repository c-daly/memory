# memory — project context

## Thesis

Claude Code plugin providing durable agent observation memory — `user`, `feedback`, `project`, `reference` notes that persist across sessions. Sovereign and self-contained: no cross-plugin runtime dependencies. Storage via a configurable `Provider` interface; ships `VaultProvider` (default; PARA-aware) and `FilesystemProvider` (test fixture).

GitHub: `c-daly/memory`. Re-derived after the original 2026-05-09 plan was lost in a desktop spill (see vault loss record).

## Current state

- **v1.0.0** shipped 2026-05-12 (providers, MEMORY.md index, reader/writer, CLI, FastMCP server).
- **T3 — provider-root append locking** shipped 2026-05-17 (advisory `.memory.lock`, re-entrant, PID-checked stale recovery).
- **Audit #6 — entity-locality enforcement** shipped 2026-05-17. The inbox fallback in `VaultProvider._resolve_subject_folder` was replaced with a hard `MemorySubjectNotFoundError`; an optional alias registry at `<vault>/.memory-aliases.yaml` handles naming drift.

See `<vault>/10-projects/memory/narrative.md` for the dated chronological state.

## Canonical state files (read these for project recovery)

1. `<vault>/10-projects/memory/Memory.md` — hub doc / dashboard
2. `<vault>/10-projects/memory/narrative.md` — architecture summary, current state
3. `<vault>/10-projects/constellation/2026-05-16-implementation-plan-v2.md` — current cross-plugin plan (supersedes the per-plugin v0 plans)
4. `<vault>/10-projects/memory/decisions/`:
   - `2026-05-10-two-providers-in-v0.md`
   - `2026-05-10-provider-interface-mcp-compatible.md`
   - `2026-05-10-four-entry-types-no-schema-registry.md`
   - `2026-05-12-memory-v1-minimal-contract.md`
   - `2026-05-16-append-locking-v1.md`
5. `<vault>/10-projects/memory/2026-05-09-desktop-spill-losses.md` — loss record explaining the gap in project history

## Source of truth

- **Vault is source of truth** for plans and decisions: `<vault>/10-projects/memory/{plans,decisions}/<file>.md`. Edit there directly; no dev-tree mirror.
- The constellation v2 plan (`<vault>/10-projects/constellation/2026-05-16-implementation-plan-v2.md`) is the cross-plugin doc. Per-plugin plans (memory's own `plans/` dir) are historical.
- The repo's `.claude/` tree is gitignored; old plans/decisions in git history are historical snapshots only.

## Adjacent inputs

- `<vault>/10-projects/continuity/` — continuity is memory's primary second-order consumer. When `write_provider: memory` is set in `~/.config/continuity/config.yaml`, `continuity record-insight` writes `cont.insight` artifacts through memory's CLI; default is vault-direct.
- `~/.claude/plugins/continuity/lib/memory_read_provider.py`, `memory_write_provider.py` — the bridge code that calls `bin/memory list` / `bin/memory write` as subprocesses.
- `<vault>/10-projects/continuity/decisions/2026-05-08-reader-writer-contract.md` — the cross-plugin reader/writer contract memory v1 conforms to.

## Task completion protocol

> *Stopgap until continuity provides a write-on-end mechanism.*

Trigger: when the user signals stopping or before a clean session end.

1. Append a dated entry to `<vault>/10-projects/memory/narrative.md` summarizing what shipped (commits, decisions authored, audit findings closed).
2. **Sync the vault.** `cd <vault> && git add 10-projects/memory && git commit -m "memory: <one-line summary>" && git push`. Always provide `-m`.

(No mirror step: plans and decisions are edited directly in the vault — it is the source of truth.)

## Project-specific protocols

- **`Provider` interface must accommodate non-filesystem impls** even though none ship today. Operations are substrate-agnostic — no file handles, no path manipulation in the interface — so future MCP-backed providers (Serena, memory-as-MCP) drop in cleanly.
- **PARA inbox fallback was removed in audit #6 (2026-05-17).** Subjects that don't resolve to a PARA project raise `MemorySubjectNotFoundError`; the alias registry at `<vault>/.memory-aliases.yaml` is the escape valve for naming drift. Real PARA dirs always win over aliases.
- **Append-only.** No `delete()`, no `update()`. Corrections are new entries that consumers reconcile. v2 layout (`<entity>/.memory/<date>-<name>.md`) has TWO collision checks:
  1. **Logical:** the `exists(name, type)` check raises `MemoryCollisionError` if any entry with the same (name, type) already exists — applies across dates per provider.
  2. **Physical:** the path is `<date>-<name>.md` with no type segment, so same (name, date) under the same entity collides on filename regardless of type.
  Use distinct names if you need to differentiate same-day entries that share a name.
- **Lock semantics.** Provider-root advisory lockfile `.memory.lock` covers `write → put → index.append` as one critical section, plus `index.rebuild_from_scan`. Re-entrant per thread+root. Same-host stale locks recover only when the recorded PID is proven dead; cross-host or unreadable locks are left in place.
