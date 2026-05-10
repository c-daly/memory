# memory — project context

## Thesis

Claude Code plugin providing durable agent observation memory — `user`, `feedback`, `project`, `reference` notes that persist across sessions. Sovereign and self-contained: no cross-plugin runtime dependencies. Storage via configurable `Provider` interface; v0 ships two filesystem-backed providers (`FilesystemProvider`, `VaultProvider`).

GitHub: `c-daly/memory`. Re-derived after the original 2026-05-09 plan was lost in a desktop spill (see vault loss record).

## Canonical state files (read these for project recovery)

1. `<vault>/10-projects/memory/Memory.md` — hub doc / dashboard
2. `<vault>/10-projects/memory/narrative.md` — architecture summary, current state
3. `<vault>/10-projects/memory/plans/2026-05-10-memory-v0.md` — current implementation plan (supersedes the re-derivation attempt)
4. `<vault>/10-projects/memory/plans/2026-05-10-memory-v0-rederived.md` — first re-derivation; preserved as historical record (not the plan to follow)
5. `<vault>/10-projects/memory/2026-05-09-desktop-spill-losses.md` — loss record explaining the gap in project history
6. `<vault>/10-projects/memory/decisions/` — architectural decisions (currently empty; populate during Phase 0)

## Source of truth vs vault snapshots

- **Source of truth:** `~/projects/memory/.claude/{plans,decisions}/<file>.md` (where edits happen on this Mac).
- **Vault snapshots:** `<vault>/10-projects/memory/{plans,decisions}/<file>.md` (the cross-machine durable record).
- **Sync is manual** until continuity itself is built. After editing source-of-truth, copy to vault and commit + push the vault. The current plan mirror at `.claude/plans/2026-05-10-memory-v0.md` was bootstrapped from the vault copy — keep them in sync going forward.

## Adjacent inputs (intact and authoritative)

These survived the spill at `~/projects/continuity/`; the v0 plan references them and they should be re-read when context is needed:

- `continuity/.claude/decisions/2026-05-07-memory-as-own-plugin.md` — the foundational decision establishing memory as its own plugin
- `continuity/.claude/plans/2026-05-08-reader-writer-architecture.md` — the cross-plugin reader/writer contract memory v0 conforms to
- `continuity/lib/` — Phase 1 reference shape; the `~/projects/continuity/lib/` layout was the model for this scaffold

## Session start protocol

> *Stopgap until continuity's resume-brief covers this project automatically. Remove when `~/.claude/plugins/continuity/bin/continuity resume-brief memory` returns non-empty.*

Trigger: every session whose cwd is at or below `~/projects/memory/`, before responding to the first user message.

1. `tail -120 <vault>/10-projects/memory/narrative.md` — read latest state.
2. Read `<vault>/10-projects/memory/plans/2026-05-10-memory-v0.md` — current plan; identify the next un-checked phase / item.
3. List `<vault>/10-projects/memory/decisions/` — which decisions exist; what's pending.
4. Briefly acknowledge the current phase + next concrete item in the first response.

## Task completion protocol

> *Stopgap until continuity provides a write-on-end mechanism.*

Trigger: when the user signals stopping or before a clean session end.

1. Append a dated entry to `<vault>/10-projects/memory/narrative.md` summarizing what shipped (Phase x.y items, commits, decisions authored).
2. If a decision was authored, mirror it from `~/projects/memory/.claude/decisions/<file>.md` to `<vault>/10-projects/memory/decisions/<file>.md`.
3. If the implementation plan was edited (rare — usually only between phases), mirror from `~/projects/memory/.claude/plans/<file>.md` to `<vault>/10-projects/memory/plans/<file>.md`.
4. **Sync the vault.** `cd <vault> && git add 10-projects/memory && git commit -m "memory: <one-line summary>" && git push`. Always provide `-m`.

## Project-specific protocols

- **Phase 0 has three decisions to author** (per the current plan): two-providers-in-v0, provider-interface-MCP-compatible, four-entry-types-no-schema-registry. These should be written before Phase 1 starts.
- **Don't re-derive `2026-05-09-sample-providers-in-lib-providers.md`** — it was lost; the current plan deliberately doesn't treat it as load-bearing. The decision it captured (sample-providers-in-`lib/providers/`) is now a packaging detail, not architecture.
- **`Provider` interface must accommodate non-filesystem impls** even though none ship in v0. Operations should be substrate-agnostic — no file handles, no path manipulation in the interface — so future MCP-backed providers (Serena, memory-as-MCP) drop in cleanly.
- **Migration target on this Mac:** five intact memory dirs at `~/.claude/projects/-Users-cdaly-*/memory/` are valid corpora. The original migration target (12 dirs at `~/.claude/projects/-home-fearsidhe-*/memory/`) was lost in the spill.
