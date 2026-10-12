---
name: qa-gate
description: >-
  Full quality gate workflow run after every completed feature. Runs automated
  tests, linters, coverage, Golden Bills accuracy (if scanning changed), browser
  flows, and QC review. Produces a Gate Report (PASS or FAIL) and either
  approves the merge or sends issues back to the builder.
trigger: slash_command
---

# /qa-gate Workflow

**Who runs this:** QA Agent, then Browser QA Agent, then QC Agent.

> For detailed step-by-step instructions, read the skill: `.agents/skills/qa-gate/SKILL.md`

## Quick Steps

1. **QA Agent** — run automated checks:
   - `pytest -q`
   - `ruff check . && ruff format --check .`
   - `python manage.py check`
   - `python manage.py makemigrations --check --dry-run`
   - Coverage: ≥ 80% overall, ≥ 95% on money/extraction code.
   - If scanning code changed: `pytest tests/test_golden_bills.py -v` (grand total + date ≥ 95%).
   - Add missing edge-case tests where needed.

2. **Browser QA Agent** — run the user-flow checklist (desktop + mobile, EN + UR). Attach screenshots.

3. **QC Agent** — review diff against the 9-item QC checklist in the qa-gate skill. Score each PASS/FAIL.

4. **Output Gate Report** — PASS or FAIL (see format in qa-gate skill).

5. **If FAIL** — return issues to the owning builder. Re-run `/qa-gate` after fixes. Maximum 3 loops, then escalate.

6. **If PASS** — Lead Architect merges to `main`. Update `docs/PROGRESS.md`.
