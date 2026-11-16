@AGENTS.md

## Claude Code

- Run the quality gates only through the `quality-gates` agent. For issue-scoped runs, name the tests and ask for tests only; before a task is done, ask for the full gates (the same checks as `uv run poe check`). Don't run them directly in the shell.
- After creating or editing files, have them reviewed, including any edits made in response to an earlier review: Markdown documents (including skills, agent definitions and agent memory) by the `doc-reviewer` agent, and everything else by the `code-reviewer` agent. Run both when a change touches both. Propose fixes for their findings and wait for approval before applying them.
