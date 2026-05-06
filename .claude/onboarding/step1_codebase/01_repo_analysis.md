# Step 1 — Repo Analysis (Brownfield)

## Project: MiroFish
Multi-Agent Swarm Intelligence Prediction Engine.

## Date: 2026-05-06

## Findings

### Top-level Structure
```
MiroFish/
├── .claude/              # Claude Code config (Step 0 set up)
├── .codegraph/           # local index, gitignored
├── .github/workflows/    # CI
├── backend/              # Python (Flask, uv)
│   ├── app/{api,services,models,utils,config}
│   ├── pyproject.toml, requirements.txt, run.py, uv.lock
│   └── scripts/
├── frontend/             # Vue 3 + Vite
│   ├── src/{api,components,views,router,store,i18n,assets}
│   ├── package.json, vite.config.js, index.html
│   └── public/
├── locales/, static/
├── package.json          # root orchestrator (concurrent dev)
├── docker-compose.yml, Dockerfile
├── README.md, README-EN.md, README-ZH.md
├── CLAUDE.md
└── LICENSE
```

### Decisions

| Question | Decision |
|----------|----------|
| Q1 — Structure changes? | **No changes**. Existing layout is intentional and aligns with the layer-based convention from the Salestech Dev Guidelines. |
| Q2 — Create `docs/`? | **No**. Documentation stays in `README*.md`, `CLAUDE.md`, and `.claude/onboarding/`. |
| Q3 — Keep `.claude/`? | **Yes, keep as-is** (configured during Step 0). |
| Q4 — `.gitignore` additions? | **No further changes**. Step 0 already updated `.gitignore` to track project-level `.claude/` and ignore `settings.local.json` and `.codegraph/`. |
| Q5 — Trilingual README? | **Keep** the three READMEs (`README.md` = English default, `README-EN.md` = explicit EN, `README-ZH.md` = Chinese). |

### Already Configured (from Step 0)
- `.claude/settings.json` — permissions (allow safe bash, deny secrets / destructive cmds)
- `.claude/rules/` — markdown, file-paths, commits, error-handling, dev-guidelines
- `.gitignore` — tracks project-level `.claude/`, ignores `settings.local.json` + `.codegraph/`

## Next
- **PROMPT 2:** Review / update `CLAUDE.md` (tech stack, conventions, architecture, commands).
- **PROMPT 3:** Review / update `README.md` (prerequisites, env vars, install).
