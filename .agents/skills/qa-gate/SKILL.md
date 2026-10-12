---
name: qa-gate
description: >-
  Full QA → QC gate workflow. Use when a builder finishes a feature and hands
  off for review. Runs the full test suite, linters, migration check, coverage
  report, browser tests, and QC review. Produces a Gate Report (PASS or FAIL).
---

# QA Gate Skill

This skill runs the full quality gate for a finished feature. It involves three stages: QA Agent review, Browser QA Agent review, and QC Agent final approval.

## When to Use

Trigger this skill every time a builder agent finishes a task and says "ready for review."

## Stage 1 — QA Agent (automated checks)

1. **Run the full test suite:**
   ```bash
   pytest -q
   ```
   Record: number of tests, failures, errors, warnings.

2. **Run linters:**
   ```bash
   ruff check .
   ruff format --check .
   ```

3. **Check Django health:**
   ```bash
   python manage.py check
   python manage.py makemigrations --check --dry-run
   ```

4. **Check coverage:**
   ```bash
   pytest --cov=. --cov-report=term-missing -q
   ```
   Required: ≥ 80% overall; ≥ 95% on `bills/`, `ledger/`, `scanning/` (money + calculation code).

5. **If scanning code changed:** run the Golden Bills accuracy test.
   ```bash
   pytest tests/test_golden_bills.py -v
   ```
   Required pass lines: grand total ≥ 95%, date ≥ 95%, items ≥ 90% on printed bills.

6. **Add missing edge-case tests** if any checklist item from `.agents/rules/10-quality-gate.md` is uncovered.

## Stage 2 — Browser QA Agent (UI flows)

Run the following flows. On desktop (≥ 1280 px) AND phone (375 px). In English AND Urdu.

1. Login as Super Admin → see dashboard.
2. Login as Staff → verify restricted actions are hidden/blocked.
3. Create a staff account (as Super Admin).
4. (Phase 4+) Upload a printed bill → confirm AI extraction → verify review screen.
5. (Phase 4+) Upload a handwritten bill → confirm extraction.
6. (Phase 4+) Upload a 3-image bill → confirm single merged result.
7. Add a manual bill → confirm it appears in bill list.
8. Add a payment → confirm ledger updates.
9. View vendor ledger.
10. Filter reports by date range → confirm chart updates.
11. Switch language English ↔ Urdu → confirm RTL mirrors.
12. (Phase 6+) Go offline → add a manual bill → come online → confirm sync.

For each step: take a screenshot. Record any visual glitch, broken link, page > 2 seconds, or console error.

Save test scripts in `tests/e2e/` so they can be replayed.

## Stage 3 — QC Agent (final review)

QC Agent reviews the diff against this checklist. Score each PASS or FAIL.

| # | Check |
|---|-------|
| 1 | Matches `docs/MASTER_PROMPT.md` and the task acceptance criteria. Nothing extra, nothing missing. |
| 2 | Correctness: logic, calculations (Decimal, rounding), time zones, off-by-one, null handling. |
| 3 | Data safety: no hard deletes of financial data, migrations safe, no data loss on edit or sync. |
| 4 | Security: role checks on every view/API, input and file validation, no secrets, no XSS/CSRF/SQLi gaps, private file URLs. |
| 5 | Tests: meaningful (not just coverage-filling), edge cases present, no weakened tests. |
| 6 | Performance: no N+1 queries, pagination present, indexes in place. |
| 7 | UI: English and Urdu RTL, responsive, light/dark, accessible, loading/empty/error states. |
| 8 | Maintainability: readable, small functions, no duplicated logic, no dead code. |
| 9 | Evidence provided: test output and screenshots attached. |

## Gate Report Format

Output one of these two blocks:

**PASS:**
```
GATE REPORT — PASS
Feature: <task name>
QA: all tests pass, coverage 85% overall / 96% on money code.
Browser QA: all 12 flows completed. Screenshots attached.
QC: APPROVED. No Critical or High issues.
Issues (Medium/Low, non-blocking): <list or "none">
Ready to merge.
```

**FAIL:**
```
GATE REPORT — FAIL
Feature: <task name>
Issues:
  [CRITICAL] <file:line> — <description> — Fix required: <what to do>
  [HIGH]     <file:line> — <description> — Fix required: <what to do>
  [MEDIUM]   <file:line> — <description> — Fix required: <what to do>
Return to <owning builder agent> for fixes. Re-run /qa-gate after fixes.
Loop count: <1, 2, or 3>. If loop count = 3, escalate to owner.
```

## Fix Loop Limit

Maximum **3 loops** of (fix → re-run qa-gate). After 3 failures, stop and escalate to the product owner with a plain-language summary of the blocker.
