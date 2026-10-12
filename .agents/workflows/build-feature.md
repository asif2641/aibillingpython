---
name: build-feature
description: >-
  Builder + QA workflow for implementing a single approved task. QA writes
  failing tests first (test-first), then the builder implements the minimum
  code to pass them, runs the quality-gate commands, and hands off to /qa-gate.
trigger: slash_command
---

# /build-feature Workflow

**Who runs this:** QA Agent first, then the assigned Builder Agent.

## Steps

### Step 1 — QA Agent: Write Failing Tests First

Before the builder writes a single line of feature code:

1. Read the task description and acceptance criteria from the phase plan.
2. Write tests in `tests/` that will **fail** right now (because the feature doesn't exist yet).
3. Cover at minimum:
   - Happy path (the normal, expected use)
   - 3 edge cases (boundary values, empty/missing data, huge values, wrong types)
   - 1 failure/error case (what happens when something goes wrong)
   - Permission case (staff vs Super Admin if relevant)
4. Run `pytest -q` — confirm the new tests **fail** (this proves the tests are real).
5. Hand off to the builder with: "Tests written and failing. Ready for implementation."

### Step 2 — Builder: Implement

1. Write the **minimum code** required to make the failing tests pass.
   - Models: in the owning app's `models.py`.
   - Business logic: in `services.py` (not in views, not in templates).
   - Views: thin — call service functions, return responses.
   - Templates: no business logic.
2. Run tests frequently while implementing.

### Step 3 — Builder: Run Quality Gate Commands

Run all of these and fix every failure:

```bash
pytest -q
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

Check coverage:
```bash
pytest --cov=. --cov-report=term-missing -q
```

Fix until:
- 0 test failures
- 0 linter errors
- 0 Django system check errors
- No pending migrations detected

### Step 4 — Hand Off

**Do not mark the task done yourself.** Instead:

1. Write a short handoff message:
   ```
   TASK COMPLETE — ready for /qa-gate
   Task: <task name>
   Tests: <N> new tests, all passing
   Coverage: <X>% overall, <Y>% on critical code
   Files changed: <list>
   ```
2. Trigger `/qa-gate`.
