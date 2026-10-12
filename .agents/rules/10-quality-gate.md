# Quality Gate — a task is DONE only when ALL items below are true

## 1. Tests Written

- [ ] New feature has a test for the **happy path**.
- [ ] At least **3 edge cases** covered (boundary values: 0, negative, huge numbers, decimals, empty/missing data, wrong file types, huge files, duplicate submissions, double-clicks).
- [ ] At least **1 failure/error case** covered (what happens when it goes wrong).
- [ ] Permissions tested: same action by Staff vs Super Admin gives the correct result.
- [ ] Urdu and mixed-language text tested where relevant.
- [ ] Date/time zone edge cases tested where relevant.

## 2. All Commands Exit 0

Run these in order. Fix every failure before handing off.

```bash
pytest -q
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

If mypy or pyright is configured:
```bash
mypy <changed_files>
```

## 3. Coverage

- Overall coverage: **≥ 80%**
- Money / ledger / extraction-validation code: **≥ 95%**

Run coverage:
```bash
pytest --cov=. --cov-report=term-missing -q
```

## 4. Code Quality

- [ ] No `TODO` or `FIXME` comments left in the code.
- [ ] No placeholder code (`pass`, `...`, `# add code here`).
- [ ] No commented-out code.
- [ ] No `print()` debug statements.

## 5. UI Checklist (for any template or static change)

- [ ] Tested in **English (LTR)** layout.
- [ ] Tested in **Urdu (RTL)** layout — all elements mirror correctly, text is readable.
- [ ] Tested at **desktop width** (≥ 1280 px).
- [ ] Tested at **phone width** (375 px).
- [ ] Tested in **light mode**.
- [ ] Tested in **dark mode**.
- [ ] Loading state shown while data fetches.
- [ ] Empty state shown when there is no data.
- [ ] Error state shown when something fails.
- [ ] Screenshots attached as evidence.

## 6. Security Checklist (for every change)

- [ ] Every view/API has a `@login_required` (or `LoginRequiredMixin`) guard.
- [ ] Role checked where Super Admin vs Staff matters.
- [ ] All user input validated (forms, query params, file uploads).
- [ ] File uploads: type checked by content (not extension), size ≤ 15 MB.
- [ ] No secrets in code; using `.env` variables.
- [ ] No SQL injection risk (using Django ORM, not raw strings).
- [ ] CSRF protection on all state-changing forms.

## 7. QC Approval

- [ ] QC Agent has reviewed the diff against all checklist items above.
- [ ] Gate Report verdict is **APPROVED** (no open Critical or High issues).

## 8. Evidence Attached

- [ ] Paste of `pytest -q` output showing 0 failures.
- [ ] Coverage summary.
- [ ] Screenshots for any UI changes (desktop + mobile, EN + UR, light + dark).

---

> **If any item above is not checked, the task is NOT done. Do not merge. Do not self-approve.**
