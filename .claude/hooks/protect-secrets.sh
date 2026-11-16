#!/usr/bin/env bash
# A best-effort safety net for the AGENTS.md rule never to open secrets or
# .env files, not a guarantee. It refuses the Read, Edit, Write and Grep tools
# on a file named .env or .env.<anything>, and a shell command that names one.
# .env.example is allowed, as AGENTS.md requires it to be kept up to date.
# - It only knows the .env naming; other secret files aren't recognised.
# - A shell command that reaches a .env file without naming it plainly, such
#   as through a glob or a name broken up with quotes, isn't caught; tools
#   that load .env themselves, like Docker Compose, are unaffected. Grep
#   across a directory skips .env because it's git-ignored.
# - For shell commands it only runs when the `if: "Bash(*env*)"` filter in
#   settings.json matches a part of the command. A here-document's body isn't
#   always part of that match, so a command inside one may not be checked.
# - A shell command that only mentions a .env name, such as a commit message
#   passed with -m, is refused too; pass such text through a file instead.
# - It fails open: a missing jq or unreadable input is allowed through.
input="$(cat)"
tool="$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null)"

deny() {
  jq -n --arg reason "$1" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
  exit 0
}

reason="AGENTS.md says never to open secrets or .env files; .env.example is allowed."

# Whether a path's file name is .env or .env.<suffix>, other than .env.example.
is_secret() {
  local name
  name="$(basename -- "$1")"
  [[ "$name" == ".env" || ( "$name" == .env.* && "$name" != ".env.example" ) ]]
}

# Whether a path, or the file a symlink at it points to, is a secret.
is_secret_path() {
  is_secret "$1" || is_secret "$(realpath -m -- "$1")"
}

case "$tool" in
  Read|Edit|Write)
    path="$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null)"
    [[ -n "$path" ]] && is_secret_path "$path" && deny "$reason"
    ;;
  Grep)
    path="$(jq -r '.tool_input.path // empty' <<<"$input" 2>/dev/null)"
    [[ -n "$path" ]] && is_secret_path "$path" && deny "$reason"
    glob="$(jq -r '.tool_input.glob // empty' <<<"$input" 2>/dev/null)"
    [[ "$glob" == *.env* && "$glob" != *.env.example ]] && deny "$reason"
    ;;
  Bash)
    command="$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null)"
    # Split the command into words at characters that can't be part of a file
    # name, then check each word as a path.
    while read -r word; do
      [[ -n "$word" ]] && is_secret "$word" && deny "$reason"
    done < <(tr -s "[:space:];&|()<>\"'\`=,:\\\\" '\n' <<<"$command")
    ;;
esac
exit 0
