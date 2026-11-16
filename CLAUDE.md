@AGENTS.md

## Claude Code

- Run the quality gates only through the `quality-gates` agent. For issue-scoped runs, name the tests and ask for tests only; before a task is done, ask for the full gates (the same checks as `uv run poe check`). Don't run them directly in the shell.
- After creating or editing files, have the `code-reviewer` agent review those files, including any edits made in response to an earlier review. Propose fixes for its findings and wait for approval before applying them.
