---
date: 2026-05-10
project: memory
---

# Decision: Four hard-coded entry types in v0; no schema registry

## Decision (1 sentence)

Memory v0 supports exactly four entry types — `user`, `feedback`, `project`, `reference` — hard-coded in `memory_writer`'s validation and stored as a plain `type:` field in entry frontmatter; no schema registration mechanism, no per-type validation rules, no `mem.feedback` / `mem.user_fact` style schema names.

## Alternatives considered

- **Schema registration with typed entries** (per continuity's Phase 2 sketch in `2026-05-07-implementation-plan.md`: `mem.feedback`, `mem.user_fact`, etc., each with declared fields). *Rejected for v0.* Adds a registration phase, a per-schema validation layer, and a namespacing concern (who owns `mem.*` vs other plugins' schemas?) before any consumer has actually wanted typed schemas. The narrative explicitly chose simpler over richer (the 2026-05-09 framing) and this decision honors that.
- **Free-form `type:` field with no validation.** *Rejected.* Loses the ability to `list(type="feedback")` reliably; consumers would diverge on capitalization, pluralization, etc. Hard-coding the four matches what the existing surviving memory dirs already use, so migration is verbatim.
- **Defer the type concept entirely; everything is just a memory.** *Rejected.* `MEMORY.md` index loaded at session start works because callers can scan-by-type and pull only relevant categories. Removing the type axis collapses the index into an undifferentiated list and pushes filtering downstream.

## Why this won

The four types correspond to the four cross-conversation needs the memory system actually serves:
- `user` — who the user is, how they collaborate
- `feedback` — corrections + validations to internalize across conversations
- `project` — non-derivable facts about specific projects
- `reference` — pointers to where information lives in external systems

Adding a fifth type isn't trivial today (it's a schema design question — what does it cover, when does it apply, why isn't it one of the existing four?), so deferring schema-registration cost until that pressure exists is correct. If/when typed schemas land, they can be additive: the fifth field could be a structured `schema:` alongside the existing `type:`, and all current entries remain valid as `type` without `schema`.

This decision deliberately diverges from continuity's earlier Phase 2 sketch. Continuity's sketch was speculative; the narrative's four-types model is what every actual memory directory on disk uses today.

## Stakeholders

- c-daly
