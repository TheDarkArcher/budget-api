---
name: recurring-design-checklist-drift
description: Recurring doc issues when DESIGN.md API Design changes alongside the maintainer's local milestone checklists and review notes
metadata:
  type: feedback
---

When DESIGN.md adds, widens or drops a rule, the same rule usually lives in
other places that don't get updated with it.

**Why:** the maintainer moves checklist "Decided" behaviour into DESIGN.md in
bulk, and decisions are applied across DESIGN.md and the maintainer's local
milestone checklists and review notes in separate passes, so one copy is often
left behind.

**How to apply:**
- If the caller names a local milestone checklist, diff its rule lists (items
  and Decided section) with DESIGN.md both ways. Local working documents are
  git-ignored, so read them in full; skip this check when there are none.
- Compare DESIGN.md prose rules with the 8.7 problem-type and status-code
  tables, and flag a rule stated twice in 8.7.
- Grep for the old absolute wording elsewhere ("there is no manual ordering",
  "fire on UPDATE only") whenever a rule is loosened or widened, and test
  absolute claims against the ordered checks next to them (Error order).
- When a planned change is dropped, grep the checklist for every line that
  depends on it, not just the line that states it.
- For an "Enforced in: Database" rule that changes, grep the committed
  migration: the claim stays false until a new migration exists.
- In review notes with a Decisions section, check the Summary, intro and
  "Questions" wording still reads as settled, and the tense matches what has
  been applied.
- Check a checklist's "Source:" line lists every DESIGN.md section its items
  cite.
