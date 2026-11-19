@AGENTS.md

## Claude Code

- After a code change, have the `quality-gates` agent check the quality gates rather than checking them in the main session. For issue-scoped runs, name the test files and ask for tests only; before a task is done, ask for the full gates (the same checks as `uv run poe check`). The main session and other agents may run an individual check, such as one test or `ruff check`, directly when their own work needs it.
- For a change in behaviour, run the new tests directly to see them fail before the code, and again to see them pass after it. Then have `quality-gates` run the test files they're in.
- After creating or editing files, have them reviewed, including any edits made in response to an earlier review: Markdown documents (including skills and agent definitions) by the `doc-reviewer` agent, and everything else by the `code-reviewer` agent. Run both when a change touches both. Also run the `api-consumer-reviewer` agent, after `openapi.json` is re-exported, for changes to `openapi.json` or to the "Domain Rules" or "API Design" sections of `docs/DESIGN.md`. Propose fixes for their findings and wait for approval before applying them. Propose changes to `docs/DESIGN.md` through the `design-doc` skill.
- Agent memory (`.claude/agent-memory/`) is exempt from the review-after-each-edit rule and from the wait-for-approval rule: `doc-reviewer` reviews it once, before the commit that includes it, because reviewers update their own memory on most runs. Apply its fixes without waiting for approval.
