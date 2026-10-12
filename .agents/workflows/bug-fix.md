---
name: bug-fix
description: >-
  Bug fix workflow. Use when a bug is reported. Ensures the bug is reproduced
  with a failing test first, root-caused, fixed at the source, and documented
  before merging. Never patch symptoms.
trigger: slash_command
---

# /bug-fix Workflow

**Who runs this:** The agent that owns the affected folder.

> For detailed steps, read the skill: `.agents/skills/bug-triage/SKILL.md`

## Quick Steps

1. **Reproduce first:** Write a failing test that proves the bug exists. Do not touch feature code yet.

2. **Root cause:** Identify why it happens (not just where it crashes). Write the hypothesis in a comment.

3. **Fix:** Make the minimum change to fix the root cause. Confirm the failing test now passes.

4. **Full suite:** Run `pytest -q` — no regressions allowed.

5. **Run linters:**
   ```bash
   ruff check .
   ruff format --check .
   python manage.py check
   ```

6. **Document:** Add an entry to `docs/BUG_LOG.md` with: what, why, how fixed, regression test name.

7. **Hand off:** Run `/qa-gate` as normal. The regression test must appear in the Gate Report evidence.

## Severity Reminder

| Severity | Meaning |
|----------|---------|
| Critical | Data loss, wrong money totals, security hole |
| High | Feature broken, no workaround |
| Medium | Annoying but has a workaround |
| Low | Cosmetic |

> If a bug is Critical or High, notify the Lead Architect immediately before fixing, so the owner can be informed.
