#!/usr/bin/env zsh
# PreCompact / SessionEnd hook — fire the informed recorder.
# Reads CC hook JSON from stdin (contains .transcript_path). Never crashes the
# session: any failure exits 0 silently (recording is best-effort).
#
# Loop-guard: the recorder runs `claude -p`, which is itself a CC session and
# would re-fire this hook. MEMORY_RECORDING=1 (set by the recorder) makes this
# hook a no-op inside that nested session.
set -uo pipefail

# Loop-guard: do nothing if we are already inside a recorder-spawned session.
if [[ "${MEMORY_RECORDING:-0}" == "1" ]]; then
  exit 0
fi

input="$(cat)"
transcript="$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null)"
[[ -z "$transcript" || ! -f "$transcript" ]] && exit 0

script_dir="${0:A:h}"
memory_root="${MEMORY_ROOT:-${script_dir:h}}"
memory_bin="$memory_root/bin/memory"
[[ -x "$memory_bin" ]] || exit 0

# Best-effort, time-bounded, fully detached from the session's success.
"$memory_bin" record --transcript "$transcript" >/dev/null 2>&1 || true
exit 0
