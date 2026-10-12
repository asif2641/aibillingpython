---
name: release-check
description: >-
  Full release readiness check before deploying to a new stage (free server or
  live server). Runs the full QA gate, dependency vulnerability scan, secret
  scan, deployment settings check, database backup/restore test, and a smoke
  test on the target server. Only the owner can approve the release.
trigger: slash_command
---

# /release-check Workflow

**Who runs this:** QC Agent + Security & DevOps Agent.

> Run this before every deployment to a new stage (local → free server, free → live).

## Step 1 — Full QA Gate on `main` branch

Run `/qa-gate` on the current `main` branch. It must produce a **PASS** Gate Report. No exceptions.

## Step 2 — Dependency Vulnerability Scan

```bash
pip-audit
```

Fix any Critical or High vulnerabilities before proceeding. Log Medium/Low in the Release Report.

## Step 3 — Secret Scan

Scan the repository for accidentally committed secrets:

```bash
# Install if not present:
pip install detect-secrets
detect-secrets scan --all-files > .secrets.baseline
detect-secrets audit .secrets.baseline
```

Also manually verify:
- [ ] `.env` is listed in `.gitignore`
- [ ] `git log --all -p | grep -i "api_key\|secret\|password"` returns nothing suspicious

## Step 4 — Django Deployment Check

```bash
python manage.py check --deploy
```

All warnings must be resolved. Common items: `DEBUG = False`, `ALLOWED_HOSTS` set, `SECRET_KEY` from env, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

## Step 5 — Database Backup and Restore Test

1. Take a backup of the current database.
2. Restore it to a fresh database.
3. Run `python manage.py check` and `pytest -q` against the restored database.
4. Confirm the restore succeeded (no data loss, all tables present).

## Step 6 — Smoke Test on Target Server

After deploying to the target server, manually verify:

- [ ] Site loads over HTTPS without certificate warnings.
- [ ] Login as Super Admin works.
- [ ] Dashboard loads with correct numbers.
- [ ] Upload one test bill and confirm it processes.
- [ ] Add one manual bill and confirm it saves.
- [ ] Static files load (CSS, JS, fonts).
- [ ] No 500 errors in the server logs.

## Step 7 — Release Report

Produce a Release Report in this format:

```
RELEASE REPORT — <stage name> — <date>
═════════════════════════════════════
QA Gate:          PASS / FAIL
pip-audit:        PASS / N issues found
Secret scan:      PASS / N issues found
manage.py check --deploy: PASS / N warnings
DB backup/restore:  PASS / FAIL
Smoke test:       PASS / FAIL

Issues (non-blocking):
  - <list>

Recommendation: READY TO DEPLOY / BLOCKED
```

> ⏸ **Only the product owner can approve the release** after reading this report.
> Do not deploy without the owner's explicit "approved" reply.
