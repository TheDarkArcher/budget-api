---
name: pull-request
description: Prepare, open and follow up a pull request in this repository - bring the branch up to date, check it is ready, push and open the PR, watch CI and clean up after merge. Use whenever pushing a branch for review, opening or updating a PR, or once a PR is merged.
---

# Pull requests in this repository

The rules are in the Git section of `AGENTS.md` and the "Git workflow" and "Versioning" sections of `docs/DESIGN.md`. This skill is the procedure for following them; where the two differ, the rules win. Push and open pull requests only when the maintainer asks. A request to open or update a pull request is also the request to push its branch, including a force-push after a rebase, to that branch only.

## 1. Bring the branch up to date
- Make sure every change for this issue is committed and no tracked file has uncommitted changes. Untracked files don't matter.
- Run `git fetch`.
- A branch with no commits of its own is fast-forwarded with `git merge --ff-only origin/main`.
- Otherwise rebase the development branch onto `origin/main`. This skill is the maintainer's approval for a rebase that applies cleanly.
- If the rebase hits a conflict or needs a fix, stop. Show the proposed resolution as a diff and continue only once the maintainer approves it, as AGENTS.md requires.
- Don't push yet; all pushing happens in step 3, once the checks have passed.

## 2. Check the branch is ready
- It's a development branch holding only this issue's commits.
- The full quality gates pass through the `quality-gates` agent, run again after any rebase.
- Every change has been reviewed as CLAUDE.md requires, and docstrings are up to date.
- If an endpoint or schema changed, `openapi.json` has been re-exported.
- If the design changed, `docs/DESIGN.md` is updated, following the `design-doc` skill.
- User-visible changes, to the API or to how the project is set up and run, are in `CHANGELOG.md` under `Unreleased`, with breaking changes under their own **Breaking** heading. Agent tooling such as skills, hooks and agent definitions isn't user-visible and needs no entry.

If the changelog is missing entries:
1. Draft them in the Keep a Changelog style the file already uses, and show them to the maintainer for approval.
2. Once approved, add them and have the change reviewed, as CLAUDE.md requires.
3. Commit only `CHANGELOG.md`, with the changelog pattern in AGENTS.md. Approving the entries is the request to make this commit.
4. Continue to opening the pull request.

If anything else is missing, tell the maintainer instead of opening the pull request.

## 3. Open the pull request
- Push with `git push -u origin <branch>`. If the branch was rebased and is already on GitHub, push with `git push --force-with-lease --force-if-includes origin <branch>` instead, and only to that development branch; never force-push `main`, `staging` or `production`.
- If any push in this step is rejected, stop and tell the maintainer. Don't retry or force it; a rejected force-push means someone else has pushed to the branch.
- Open the pull request into `main` with `gh pr create`. Promotion to `staging` and `production` is a push, never a pull request.
- Count the branch's commits now, after any changelog commit from step 2.
- Title: the commit's subject for a single-commit pull request; otherwise a short subject following the same rules.
- Description: a single-commit pull request uses that commit's body, or a one-line summary if it has none. One with several commits gets one summary paragraph, then the commit subjects as a list. End with the pull request attribution line Claude Code provides.
- Write the description to a file in the scratchpad directory and pass it with `--body-file`.

## 4. Follow up
- Check CI with `gh pr checks <number> --watch` and report the result, with the likely cause of any failure.
- To update an open pull request, follow steps 1 and 2, then push as in step 3.
- When the maintainer says the pull request is merged, tidy up without asking:
  1. Confirm with `gh pr view <number> --json state,headRefOid` that it is `MERGED` and that `headRefOid` matches the local branch's tip.
  2. Run `git switch main`, then `git fetch --prune`.
  3. Fast-forward local `main` with `git merge --ff-only origin/main`.
  4. Delete the local branch with `git branch -D <branch>`. `-D` is needed because a merge can give the commits new hashes; the check above has already confirmed nothing unpushed is lost.
