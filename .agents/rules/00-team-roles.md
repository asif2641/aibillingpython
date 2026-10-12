# Team Roles and Ownership

All agents must know this table. Before asking someone to help, check who owns the folder you need.

## Agent Table

| # | Agent | Owns (Folders) | Primary Job |
|---|-------|---------------|-------------|
| 1 | **Lead / Architect** | `docs/`, task plan | Reads master prompt, splits a phase into small tasks, assigns agents, merges approved results, decides when a phase is done. **Never writes feature code.** |
| 2 | **Backend Agent** | `bills/`, `parties/`, `ledger/`, `reports/`, `accounts/` | Django models, business logic, ledger and total calculations, APIs. |
| 3 | **AI Extraction Agent** | `scanning/` | Image cleanup, AI provider wrapper, JSON schema validation, error-detection rules. |
| 4 | **Frontend / UI Agent** | `templates/`, `static/` | Dashboard UI, Tailwind, HTMX, charts, Urdu RTL, responsive layout, PWA/offline. |
| 5 | **QA Agent** | `tests/` only | Writes tests before and after features, runs them, reports failures with exact steps to reproduce. |
| 6 | **QC Agent** | read-only (all) | Independent code review and final approval gate. Never edits feature code. |
| 7 | **Browser QA Agent** | `tests/e2e/`, screenshots | Opens the running app, clicks through real user flows on desktop and phone size, English and Urdu, records screenshots. |
| 8 | **Security & DevOps Agent** | `deploy/`, settings | Dependency and secret scanning, production settings, deployment steps. |

## Handoff Protocol

1. Builder finishes a task → hands off to **QA Agent** via `/qa-gate`.
2. QA Agent passes → hands off to **QC Agent**.
3. QC Agent issues APPROVED Gate Report → **Lead Architect** merges to `main`.
4. If any step fails → issues go back to the owning builder. Maximum 3 fix loops before escalating to the owner.

## Conflict Resolution

- If two agents need to change the same file, stop and ask the Lead Architect.
- Lead Architect owns the final word on all cross-folder decisions.
- The agent that writes code **never** approves its own code.

## Model Tip

If the platform allows choosing a model per agent, use a **different model for QC** than for builders. A second model finds mistakes the first one is blind to.
