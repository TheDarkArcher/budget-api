#!/usr/bin/env bash
# A best-effort safety net, not a guarantee; the Git rules in AGENTS.md are the
# real control. Refuses a git commit, --amend included, while the repository the
# command runs in is on a protected branch.
# - It checks the command's working directory, falling back to the project
#   folder, but doesn't follow a `cd` or `-C` inside the command.
# - It only runs for commands that the `if: "Bash(git *)"` filter in
#   settings.json lets through. Each part of a chained command is checked on
#   its own, but a part that doesn't start with git, such as `sh -c '...'` or
#   `env X=1 git ...`, never reaches it.
# - It misses unusual forms such as git aliases, line continuations and full
#   paths to git.
# - It fails open: a missing jq, unreadable input, a detached HEAD or a
#   directory that isn't a repository is allowed through.
# - Other commands that create commits (merge, cherry-pick, revert, rebase)
#   aren't checked.
input="$(cat)"
command="$(jq -r '.tool_input.command // empty' <<<"$input" 2>/dev/null)"
cwd="$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)"

# The git subcommand is commit, allowing for options before it such as -C <dir>,
# and for git starting a command, a quoted string or a backtick substitution.
edge="[;&|()\`\"'[:space:]]"
options="([[:space:]]+(-C|-c|--git-dir|--work-tree|--namespace)[[:space:]]+[^[:space:]]+|[[:space:]]+-[^[:space:]]+)*"
pattern="(^|${edge})git${options}[[:space:]]+commit(${edge}|\$)"
[[ "$command" =~ $pattern ]] || exit 0

branch="$(git -C "${cwd:-${CLAUDE_PROJECT_DIR:-.}}" branch --show-current 2>/dev/null)"
case "$branch" in
  main|staging|production)
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Commits on the protected branch %s are not allowed. Commit on a development branch instead (see Git in AGENTS.md)."}}' "$branch"
    ;;
esac
