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
6. `<vault>/10-projects/memory/decisions/` — architectural decisions (Phase 0: three decisions authored on 2026-05-10 — two-providers-in-v0, provider-interface-MCP-compatible, four-entry-types-no-schema-registry)

## Source of truth

- **Vault is source of truth** for plans and decisions: `<vault>/10-projects/memory/{plans,decisions}/<file>.md`. Edit there directly; no dev-tree mirror.
- The repo's `.claude/{plans,decisions}/` is now redundant with the vault and is being phased out (gitignored going forward); existing tracked copies will be removed in a follow-up commit. Treat tracked copies in git history as historical snapshots only.
- The pre-spill convention treated `~/projects/memory/.claude/{plans,decisions}/` as source of truth with vault as snapshot. That convention is reversed as of 2026-05-12: vault is canonical, dev tree is not.

## Adjacent inputs

The v0 plan references these; re-read when context is needed. Continuity's `.claude/` tree was gitignored in the repo and the only copy was lost in the 2026-05-09 spill — its plans/decisions live in the vault:

- `<vault>/10-projects/continuity/plans/2026-05-07-implementation-plan.md` — the constellation-level implementation plan; memory's Phase scope flows from this.
- `<vault>/10-projects/continuity/plans/2026-05-08-reader-writer-architecture.md` — the cross-plugin reader/writer contract memory v0 conforms to.
- `<vault>/10-projects/continuity/decisions/2026-05-08-reader-writer-contract.md` — the formal decision establishing the reader/writer pattern across plugins.
- `~/.claude/plugins/continuity/lib/` — Phase 1 reference shape (`vault_provider.py`, `write_provider.py`, `vault_write_provider.py`, etc.); the live code is the model for memory's scaffold.

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
2. **Sync the vault.** `cd <vault> && git add 10-projects/memory && git commit -m "memory: <one-line summary>" && git push`. Always provide `-m`.

(No mirror step: plans and decisions are edited directly in the vault — it is the source of truth.)

## Project-specific protocols

- **Phase 0 is complete** (2026-05-10): the three decisions (two-providers-in-v0, provider-interface-MCP-compatible, four-entry-types-no-schema-registry) are authored and live in `<vault>/10-projects/memory/decisions/`. Phase 1 (Provider abstraction + two filesystem-backed impls) is the next concrete work.
- **Don't re-derive `2026-05-09-sample-providers-in-lib-providers.md`** — it was lost; the current plan deliberately doesn't treat it as load-bearing. The decision it captured (sample-providers-in-`lib/providers/`) is now a packaging detail, not architecture.
- **`Provider` interface must accommodate non-filesystem impls** even though none ship in v0. Operations should be substrate-agnostic — no file handles, no path manipulation in the interface — so future MCP-backed providers (Serena, memory-as-MCP) drop in cleanly.
- **Migration target on this Mac:** five intact memory dirs at `~/.claude/projects/-Users-cdaly-*/memory/` are valid corpora. The original migration target (12 dirs at `~/.claude/projects/-home-fearsidhe-*/memory/`) was lost in the spill.
