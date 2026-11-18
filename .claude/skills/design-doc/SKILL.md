---
name: design-doc
description: Conventions for writing and editing docs/DESIGN.md - level of detail, cross-references, bold lead-ins, domain rule enforcement notes, guidance, list style and the Known Issues section. Use whenever proposing, drafting or making a change to the design document, or reviewing one.
---

# Editing the design document

`docs/DESIGN.md` is the source of truth for the project's design. The rules for when to ask before changing it are in the Design Document section of `AGENTS.md`; this skill covers how changes are written.

## Before editing
- Propose changes as a diff and wait for the maintainer's approval. When a change raises questions, find them all and ask them before drafting, not partway through.
- Keep each rule in one place. If a rule is already stated elsewhere in the document, link to it rather than repeating it.
- Domain Rules is the source of the rules. When another section, such as API Design, needs a rule that Domain Rules states, link to the Domain Rules bullet rather than restating it. Domain Rules states each rule in full; links there that only give context are fine.

## Level of detail
- Keep Domain Rules independent of the tech stack: state each rule in terms of the domain (lines, categories, items), not HTTP, query parameters, JSON fields or table names, apart from the layer names in the *Enforced in* notes. Those belong in API Design or Data Model.
- Only design-level decisions belong in the document. Implementation details stay out: index mechanics, how a rule is stored, column types and internal bookkeeping such as link archiving.
- The exception is a detail that is high-risk enough to be a design decision, such as money being `NUMERIC(12,2)`.
- State rules in terms a client of the API can see. For example: "can't be deleted while linked to an active item category", rather than describing archived link rows.
- The ER diagram defines which tables are user-owned; a table missing a `users` link there is not a gap.

## Domain rules
- Every rule in Domain Rules ends with where it is enforced: *Enforced in: X.*, optionally followed by *Checked first in: Y.* when another layer checks it earlier to give the client a clear error.
- Name the layers as the Architecture diagram labels them (Current-user resolver, HTTP handlers, Services, Data access), plus Database for PostgreSQL itself.
- Split a bullet whose parts are enforced in different places. A single rule enforced by several layers lists them all in one note, such as *Enforced in: Current-user resolver, Data access and Database.*
- Advice that nothing enforces goes in the Guidance sub-section, without an enforcement note.

## Cross-references
- Link to other sections with Markdown links using the header text, never `§x.y` numbers: `[Continuous Integration](#93-continuous-integration)`.
- When a sub-section header appears in more than one place, add the section: `[Tooling (Engineering Practice)](#92-tooling)`.
- Check that every anchor resolves after headers change.

## Formatting
- Bold at the start of a line is always a lead-in with the colon inside the bold: `**Lead-in:**`. The only exception is the first sentence of the Overview section. If a section doesn't use lead-ins, its lines don't start with bold at all. Table cells don't count.
- Sub-list items start with a capital letter, unless they open with code.
- Keep lists tight: no blank lines or indented continuation paragraphs inside a list. Fold a follow-up paragraph into the bullet's own text.
- Describe a decimal number's limits as "at most N digits, M of them decimal places", so it is clear the decimal places count towards the total.
- Name the thing being referred to rather than using "it" or "there" when another noun nearby could be meant.

## Sections with their own rules
- **Last updated:** update the date to today whenever the document is edited, as AGENTS.md requires.
- **Known Issues:** never add, change or remove entries unless the maintainer explicitly asks. The section only exists while there are known issues.
