#!/usr/bin/env zsh
# SessionStart hook — emit memory's brief as additionalContext.
#
# CC's SessionStart hooks read JSON from stdout containing a
# `hookSpecificOutput.additionalContext` field. Whatever lands there
# gets injected into the session.
#
# This hook:
#   1. Honors MEMORY_SESSION_SUMMARY=0 by emitting an empty context.
#   2. Shells out to bin/memory brief; on any failure falls through
#      to empty context rather than crashing the session
#      (omit_section per the Provider Principle).
#
# Required environment:
#   MEMORY_ROOT       — plugin install root (default: this script's parent's parent)
#   MEMORY_VAULT_DIR  — vault root used by VaultProvider
#
# Optional environment:
#   MEMORY_SESSION_SUMMARY — set to 0 to disable; default: enabled

set -uo pipefail

emit_empty() {
  printf '%s\n' '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":""}}'
  exit 0
}

if [[ "${MEMORY_SESSION_SUMMARY:-1}" == "0" ]]; then
  emit_empty
fi

script_dir="${0:A:h}"
memory_root="${MEMORY_ROOT:-${script_dir:h}}"
memory_bin="$memory_root/bin/memory"

if [[ ! -x "$memory_bin" ]]; then
  emit_empty
fi

brief="$("$memory_bin" brief 2>/dev/null)" || emit_empty

# JSON-escape via jq -Rs (raw input, slurp) so embedded quotes/newlines
# round-trip into a valid JSON string.
escaped="$(printf '%s' "$brief" | jq -Rs '.')" || emit_empty

printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":%s}}\n' "$escaped"
