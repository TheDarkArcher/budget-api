#!/usr/bin/env bash
# A best-effort safety net for two AGENTS.md rules, not a guarantee:
# - A migration that's already committed is never edited; add a new one.
# - openapi.json and uv.lock are generated and never edited by hand.
# It covers the Edit and Write tools only, so a change made through a shell
# command isn't checked. It fails open: a missing jq or unreadable input is
# allowed through, and without CLAUDE_PROJECT_DIR it treats the current
# directory as the project.
input="$(cat)"
file="$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null)"
[[ -n "$file" ]] || exit 0

project="$(realpath -m -- "${CLAUDE_PROJECT_DIR:-.}")"
file="$(realpath -m -- "$file")"
case "$file" in
  "$project"/*) relative="${file#"$project"/}" ;;
  *) exit 0 ;;
esac

deny() {
  jq -n --arg reason "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
  exit 0
}

case "$relative" in
  openapi.json)
    deny "openapi.json is generated. Regenerate it with uv run poe export-openapi instead of editing it (see AGENTS.md)."
    ;;
  uv.lock)
    deny "uv.lock is generated. Update it with uv lock or uv add instead of editing it (see AGENTS.md)."
    ;;
  migrations/versions/*.py)
    if git -C "$project" cat-file -e "HEAD:$relative" 2>/dev/null; then
      deny "$relative is already committed. Add a new migration instead of editing it (see AGENTS.md)."
    fi
    ;;
esac
