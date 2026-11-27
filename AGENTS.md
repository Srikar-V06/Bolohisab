# Working with two agents

Claude Code and Codex share the UI polish work. The plan lives in Linear: project **BoloHisaab UI polish** (team `KIR`). Issues labelled `claude-code` belong to Claude Code; issues labelled `codex` belong to Codex.

| Issue | Owner | Branch |
|---|---|---|
| KIR-5 Foundation: tokens, app shell, motion, `DESIGN.md` | Claude Code | `claude/foundation` |
| KIR-6 Speak screen | Claude Code | `claude/speak` |
| KIR-7 Customers screen | Codex | `codex/customers` |
| KIR-8 Receipts screen | Codex | `codex/receipts` |
| KIR-9 Final QA and cross-review | Codex (Claude reviews) | `codex/qa` |

## File ownership
- **Claude Code:** `frontend/DESIGN.md`, `styles.css` (`@theme`, `@layer base`, shell, sheet, buttons, `.speak-*`, `.mic-control`, voice review cards), `App.tsx`, `components.tsx`, `voice/`.
- **Codex:** `Customers.tsx`, `Receipts.tsx`, and their sections of `styles.css` (customer, list, filter, summary, history and receipt rules).
- Both: add keys to `localization/en-IN.json` and `hi-IN.json` together. Never rename or delete a key the other agent uses.

Don't edit the other agent's files. If you need a change there, comment on the Linear issue and tag the owner.

## Rules
- KIR-5 merges first. Codex branches from `main` after it lands and follows `frontend/DESIGN.md`.
- One PR per issue into `main`. Never push to or merge into `main`; Raghu merges.
- Before opening a PR, run `npm run build` and `npm test` in `frontend/`, and check the change at 375px and 1280px in Hindi and English.
- Post status, blockers and PR links as comments on the Linear issue.

## Running locally on Windows
Port 8000 is reserved on this machine, so the Vite dev proxy can't reach a local backend. Use Docker:

```sh
docker compose up --build
docker compose exec backend python -m app.seed_demo --stitch-preview
```

Then open http://localhost:3000.
