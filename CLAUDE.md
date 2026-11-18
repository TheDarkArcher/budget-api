@AGENTS.md

## Claude Code

- After a code change, have the `quality-gates` agent check the quality gates rather than checking them in the main session. For issue-scoped runs, name the tests and ask for tests only; before a task is done, ask for the full gates (the same checks as `uv run poe check`). Other agents may run an individual check, such as one test or `ruff check`, directly when their own work needs it.
- After creating or editing files, have them reviewed, including any edits made in response to an earlier review: Markdown documents (including skills, agent definitions and agent memory) by the `doc-reviewer` agent, and everything else by the `code-reviewer` agent. Run both when a change touches both. Also run the `api-consumer-reviewer` agent, after `openapi.json` is re-exported, for changes to `openapi.json` or to the "Domain Rules" or "API Design" sections of `docs/DESIGN.md`. Propose fixes for their findings and wait for approval before applying them.
