---
name: git-commit
description: Commit changes in this repository: choose the development branch, stage only this issue's files, draft the message for approval, then commit. Use whenever committing, drafting a commit message, or creating a branch for a commit.
---

# Committing in this repository

The rules are in the Git section of `AGENTS.md` and the "Git workflow" section of `docs/DESIGN.md`. This skill is the procedure for following them; where the two differ, the rules win.

## 1. Choose the branch
- Run `git status -sb`. Never commit on a branch AGENTS.md rules out; a hook refuses it, and it must not be worked around.
- Use the current or an existing development branch when the change is related to it. Otherwise propose a new branch, named in snake_case like the existing ones (e.g. `fix_script_import_sorting`), and create it from an up-to-date `main` with `git fetch` and then `git switch -c <name> --no-track origin/main`.
- Unrelated changes go on separate branches. If the working tree holds changes for more than one issue, say which files belong where.

## 2. Stage only this issue's files
- Stage files by name; never `git add -A` or `git add .`.
- Leave unrelated and untracked files alone, and say which were left out.

## 3. Draft the message
Follow the subject and body rules in AGENTS.md. Structure the body as:
1. A paragraph on what the commit does overall and why: how things were before and what was wrong.
2. A paragraph for each changed area or set of files, saying what changed and why.
3. A paragraph on the tests added or changed and what they check. If the only test change is incidental, such as import order, cover it in its area's paragraph instead.

Never describe how something is implemented; the code shows that. Name places and things explicitly rather than "there" or "it". End with the trailer AGENTS.md requires.

First check the approved patterns listed under Git in AGENTS.md. If the commit fits one, use that pattern exactly, including its rules on the subject and body, instead of the structure above.

## 4. Get approval
Show the branch, the files and the full message, and show the full message again after every revision, not just the changed part, so it can be reviewed in context. Wait for the maintainer's approval of the message, unless it follows one of the approved patterns in AGENTS.md. Approving the message is permission to commit it, unless the maintainer says otherwise; a message that follows an approved pattern is committed only when asked.

## 5. Commit
- Write the approved message to a file in the scratchpad directory, never in the repository, and run `git commit -F <file>`, so the wrapping is kept exactly.
- Show the result with `git log -1 --stat`.
- Never push unless asked. Never amend, rebase, squash or otherwise rewrite an existing commit without the approval AGENTS.md requires.
