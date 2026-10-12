---
name: plan-phase
description: >-
  Lead Architect workflow to plan a build phase. Reads the master prompt and
  the requested phase, splits it into small tasks (≤ 1 day each), assigns each
  task to an agent, identifies which tasks can run in parallel vs in sequence,
  and presents the plan to the owner for approval before any code is written.
trigger: slash_command
---

# /plan-phase Workflow

**Who runs this:** Lead / Architect Agent only.

## Steps

### 1. Read context
- Read `docs/MASTER_PROMPT.md` — specifically the requested phase in Section 15 and its scope.
- Read `AGENTS.md` — note who owns what.
- Check `docs/PROGRESS.md` (create it if it does not exist yet) for any tasks carried over from the previous phase.

### 2. Split into tasks

For the requested phase, create a numbered task list. Each task must:
- Be completable in **≤ 1 working day**.
- Have a clear **acceptance test** (one or two sentences describing what "done" looks like for a beginner).
- Name one **owner agent** (Backend, AI Extraction, Frontend, QA, QC, Browser QA, or Security/DevOps).
- List the **files/folders** that will be created or changed.

### 3. Mark parallel vs sequential

Tasks that touch **different folders** (different agent owners) can run in parallel.
Tasks that depend on another task's output must wait — mark with "After: Task N".

### 4. Present to owner

Show the plan in this format and wait for approval:

```
PHASE <N> PLAN — <Phase Name>
═══════════════════════════════════════════════

TASK 1: <title>
  Owner:   <Agent Name>
  Folders: <list>
  Done when: <acceptance test in plain language>
  Parallel: Yes / No (After: Task X)

TASK 2: <title>
  ...

PARALLEL GROUPS:
  Group A (run together): Tasks 1, 3, 5
  Group B (run together, after Group A): Tasks 2, 4

ESTIMATED TIME: <N> tasks, roughly <N> days if parallelised.

⏸ Waiting for your approval before any code is written.
   Reply "approved" or tell me what to change.
```

### 5. After approval

- Create a `docs/PROGRESS.md` section for this phase with all tasks listed as `[ ] Not started`.
- Confirm to the owner which agents to start and in which order.
- Do not write any feature code yourself.
