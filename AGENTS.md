# Team Rules (all agents must follow)

- **Source of truth** for what to build: `docs/MASTER_PROMPT.md`. Never invent features not in the master prompt.
- **Stay in your lane.** Work only inside your owned folders. If you need a change in another agent's folder, ask the Lead Architect first.
- **Small tasks, small commits.** One feature = one git branch = one pull-request-style review.
- **Never approve your own work.** Every change must pass QA Agent review, then QC Agent review, before being merged.
- **Never skip or weaken tests.** Do not delete or comment out a failing test to make the suite pass.
- **Explain simply.** The product owner is a complete beginner. Write commit messages, comments and reports in plain language.
- **Secrets only in `.env`.** Never print, log or commit API keys, passwords or tokens.
- **Decimal for money.** Use Python `Decimal` / Django `DecimalField` everywhere money or quantities appear.
- **Soft delete only.** Never hard-delete financial records (bills, payments, ledger entries). Use `is_deleted` / trash pattern.
- **Gate before merge.** No code lands on `main` without a PASS Gate Report from QA + QC.

## Agent Ownership Map

| # | Agent | Owned Folders |
|---|-------|--------------|
| 1 | Lead / Architect | `docs/`, task plan, `AGENTS.md` |
| 2 | Backend Agent | `bills/`, `parties/`, `ledger/`, `reports/`, `accounts/` |
| 3 | AI Extraction Agent | `scanning/` |
| 4 | Frontend / UI Agent | `templates/`, `static/` |
| 5 | QA Agent | `tests/` only |
| 6 | QC Agent | read-only (all folders) |
| 7 | Browser QA Agent | `tests/e2e/`, screenshots |
| 8 | Security & DevOps Agent | `deploy/`, production settings |

## Quality Gate Summary

A task is **DONE** only when ALL pass:

1. Tests written (happy path + 3 edge cases + 1 failure case).
2. `pytest -q`, `ruff check .`, `ruff format --check .`, `python manage.py check`, `python manage.py makemigrations --check --dry-run` all exit 0.
3. Coverage ≥ 80% overall; ≥ 95% on money/ledger/extraction-validation code.
4. No TODO/placeholder/debug code.
5. UI checked in English (LTR) + Urdu (RTL), desktop + mobile, light + dark.
6. Security check passed for the change.
7. QC Agent verdict: **APPROVED**.
8. Evidence attached (test output + screenshots for UI changes).
