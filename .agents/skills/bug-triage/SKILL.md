---
name: bug-triage
description: >-
  Structured bug triage and fix workflow. Use when a bug is reported (by a user,
  a failing test, a QC rejection, or a monitoring alert). Ensures the bug is
  reproduced, root-caused, fixed at the source (not patched at the symptom),
  regression-tested, and documented before the fix is merged.
---

# Bug Triage Skill

## Step 1 — Reproduce the Bug (before touching any code)

1. Write a **failing test** that proves the bug exists. The test must fail right now on the current code.
2. Commit the failing test to a `bug/<short-name>` branch. This is the proof of the bug.
3. Never start fixing without a failing test. If you cannot reproduce it, ask the reporter for more detail.

## Step 2 — Find the Root Cause

- Read the stack trace from the top (the earliest call) not just the last line.
- Check: wrong Decimal/float conversion? Off-by-one? Missing null check? Permission not enforced? Wrong queryset?
- Write your root-cause hypothesis in a comment above the failing test before you fix it.
- Fix the **root cause**, not just the symptom (e.g., don't silence an exception if the real fix is to validate the input earlier).

## Step 3 — Fix

1. Make the minimum change that fixes the root cause.
2. Run the failing test → it must now **pass**.
3. Run the **full suite** → no other test may break.

```bash
pytest -q
ruff check .
ruff format --check .
python manage.py check
```

## Step 4 — Document in Bug Log

Add one entry to `docs/BUG_LOG.md`:

```markdown
## BUG-<number>: <short title>

- **Date:** YYYY-MM-DD
- **Reported by:** <user / agent / test name>
- **Severity:** Critical / High / Medium / Low
- **What happened:** <plain-English description>
- **Root cause:** <why it happened>
- **How fixed:** <what changed and where>
- **Regression test:** `tests/test_<module>.py::test_<name>`
```

## Step 5 — Hand off to QA Gate

After the fix, run `/qa-gate` normally. The new regression test must appear in the gate evidence.

## Severity Definitions

| Severity | Meaning | Example |
|----------|---------|---------|
| **Critical** | Data loss, wrong money totals, security hole | Grand total calculated incorrectly; SQL injection possible |
| **High** | Feature broken for real users, no workaround | Cannot upload a bill; login broken |
| **Medium** | Annoying but has a workaround | Urdu RTL layout slightly off; filter doesn't clear |
| **Low** | Cosmetic or tiny edge case | Tooltip typo; extra whitespace |
