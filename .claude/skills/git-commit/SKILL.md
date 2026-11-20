---
name: git-commit
description: Commit changes in this repository: choose the development branch, have agent memory reviewed, stage only this issue's files, draft the message for approval, then commit. Use whenever committing, drafting a commit message, or creating a branch for a commit.
---

# Committing in this repository

The rules are in the Git section of `AGENTS.md` and the "Git workflow" section of `docs/DESIGN.md`. This skill is the procedure for following them; where the two differ, the rules win.

## 1. Choose the branch
- Run `git status -sb`. Never commit on a branch AGENTS.md rules out; a hook refuses it, and it must not be worked around.
- Use the current or an existing development branch when the change is related to it. Otherwise propose a new branch, named in snake_case like the existing ones (e.g. `fix_script_import_sorting`), and create it from an up-to-date `main` with `git fetch` and then `git switch -c <name> --no-track origin/main`.
- When the change depends on a branch that isn't merged yet, create the new branch from that branch instead and tell the maintainer it is stacked, so the pull requests are merged in order. Rebasing it once that branch merges rewrites its commits, so it needs the approval AGENTS.md requires.
- Unrelated changes go on separate branches. If the working tree holds changes for more than one issue, say which files belong where.

## 2. Review agent memory
- If the files to commit include anything under `.claude/agent-memory/`, have `doc-reviewer` review them, as CLAUDE.md requires, and apply its fixes. Skip this step when no memory files are included.

## 3. Stage only this issue's files
- Stage memory files from `.claude/agent-memory/` last, after the review in step 2 has finished, because reviewers may update their memory during it.
- Stage files by name; never `git add -A` or `git add .`.
- When a file holds changes for more than one branch, stage only this branch's version of it without touching the working tree: write that version to a file in the scratchpad directory, then stage it with `git update-index --cacheinfo <mode>,<sha>,<path>`, using the SHA that `git hash-object -w <file>` prints and the mode that `git ls-files -s <path>` shows. Show the staged diff to confirm only this branch's changes are in it.
- Leave unrelated and untracked files alone, and say which were left out.

## 4. Draft the message
Follow the subject and body rules in AGENTS.md. Structure the body as:
1. A paragraph on what the commit does overall and why: how things were before and what was wrong.
2. A paragraph for each changed area or set of files that summarises what changed and why in one or two sentences. Open it with an imperative verb and the thing changed, such as "Update CLAUDE.md to …" or "Add a new agent to …", and give the reason in the same paragraph, usually with "so" or "to". Don't start a paragraph with a label such as "AGENTS.md:", and don't walk through individual edits; the diff shows those.
3. A paragraph that summarises the tests added or changed and what they check, in one or two sentences, without listing each test. If the only test change is incidental, such as import order, cover it in its area's paragraph instead.

Never describe how something is implemented; the code shows that. Name places and things explicitly rather than "there" or "it". End with the trailer AGENTS.md requires.

First check the approved patterns listed under Git in AGENTS.md. If the commit fits one, use that pattern exactly, including its rules on the subject and body, instead of the structure above.

## 5. Get approval
Show the branch, the files and the full message, and show the full message again after every revision, not just the changed part, so it can be reviewed in context. Wait for the maintainer's approval of the message, unless it follows one of the approved patterns in AGENTS.md. Approving the message is permission to commit it, unless the maintainer says otherwise; a message that follows an approved pattern is committed only when asked.

## 6. Commit
- Write the approved message to a file in the scratchpad directory, never in the repository, and run `git commit -F <file>`, so the wrapping is kept exactly.
- Show the result with `git log -1 --stat`.
- Never push unless asked. Never amend, rebase, squash or otherwise rewrite an existing commit without the approval AGENTS.md requires.
