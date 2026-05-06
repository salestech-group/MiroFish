# Salestech Products Development Guidelines

Always obey the **Salestech Products Development Guidelines**. These are
enforceable rules — non-compliant code will be rejected during review.

## Source
- Notion (Live, authoritative): https://candylabs.notion.site/development-guidelines
- Connect via Notion MCP server (HTTP requires JS, so MCP is the only reliable way).
- Always consult the live document for the latest version.

## Summary (snapshot — refer to live doc for authority)

### 1. Code Formatting & Style
- 4 spaces indentation (JS/TS and Python). No tabs.
- Max **120 chars** per line.
- No trailing whitespace; files end with a single newline.
- JS/TS: no semicolons (`semi: false`), single quotes, trailing commas
  where valid in ES5, omit parens around single arrow params.
- Python: double quotes for strings.
- Tools: Prettier + ESLint (JS/TS, npm); Ruff (Python, uv).

### 2. Naming
- JS/TS: `camelCase` vars/funcs, `PascalCase` classes/types/enums,
  `UPPER_SNAKE_CASE` constants, `kebab-case` filenames, boolean prefixes
  `is`/`has`/`should`.
- Python: `snake_case` vars/funcs/files, `PascalCase` classes,
  `UPPER_SNAKE_CASE` constants, `_leading_underscore` private.
- No abbreviations (except `id`, `url`, `http`).
- No single-letter vars (except short lambda / loop indices).
- No Hungarian notation.

### 3. Comments & Documentation
- Don't comment the obvious — comment the *why*.
- `TODO:` / `FIXME:` must include a ticket reference.
- JS/TS: JSDoc on all exported functions, classes, interfaces.
- Python: Google-style docstrings on all public funcs/classes/modules.

### 4. Git Workflow
- Branch: `<type>/<ticket-id>-<short-description>` (`feat`, `fix`,
  `chore`, `docs`, `hotfix`).
- Commits: **Conventional Commits**, lowercase, imperative, max 72 chars,
  no period, no `Co-Authored-By:` watermarks.
- PRs: linked to a ticket, ≥1 human approval, all CI checks pass,
  squash-merge feature branches, delete source branch after merge.
- Never commit directly to `main` / `dev`; never force-push shared
  branches; never commit secrets.

### 5. React & TypeScript
- Component file order: imports → types → constants → helpers →
  component.
- Named exports only; function declarations for components.
- Props types named `<ComponentName>Props`; never `React.FC`.
- Hooks start with `use`; never call hooks conditionally.
- React Router v7: file/config-based routes (don't mix), use
  `loader`/`action`, `useNavigate`, `useSearchParams`, `<Link>`,
  `<Outlet>`.
- TanStack Query: centralized query key factories, never `fetch`/`axios`
  in components, always handle loading/success/error, prefer
  `invalidateQueries` over manual cache.
- State priority: URL → TanStack Query → component state → Context.
  Never duplicate server state into local state.

### 6. Tailwind 4 (CSS-only config)
- Component styles inline as Tailwind classes; no separate CSS modules
  per component.
- Use `clsx` for dynamic classes.
- Mobile-first responsive prefixes.
- `prettier-plugin-tailwindcss` ordering required.
- No `!important` (Tailwind `!`) without justification + comment.
- `main.css` only for `@import`, `@theme`, global base styles, third-
  party overrides.

### 7. Folder Structure
- Layer-based for frontend (`api/`, `components/`, `hooks/`,
  `pages/`, `queries/`, `routes/`, `types/`, `utils/`).
- FastAPI: `routers/`, `models/`, `schemas/`, `services/`; Pydantic
  `BaseSettings`; business logic in services not routers.
- Django: `config/`, `apps/<app>/`, `common/`; one app per domain;
  business logic in `services.py`; max one migration per app per PR;
  custom User model from day 1.
- Django templates: `snake_case.html` in `templates/<app_name>/`,
  partials prefixed `_`, `{% extends %}` mandatory, DjHTML formatter,
  `{% url %}` for all URLs.
- Root directory: configuration files only.
- README.md mandatory (setup, env vars, run/test).

### 8. Accessibility
- WCAG 2.1 Level AA.
- Semantic HTML; one `<h1>` per page; no skipped heading levels.
- All images need `alt`; decorative use `alt=""`.
- 4.5:1 / 3:1 contrast minimums.
- Every form input: visible `<label>` linked via `htmlFor`/`id`.
- Keyboard accessible; native `<button>` for actions, `<a>`/`<Link>`
  for navigation.
- Custom widgets: implement WAI-ARIA pattern + keyboard handling.
- Modals trap focus and restore on close.

### 9. Environments, Secrets, Dependencies
- `.env` never committed; `.env.example` always provided and current.
- Client-exposed vars use framework prefix (e.g., `VITE_`).
- Never commit / log secrets. Rotate immediately if leaked.
- Verify a new dep is necessary; prefer well-maintained, MIT/Apache/BSD.
- No trivial deps (`is-odd`, `left-pad`, etc.).
- Lock files always committed, exact versions, no `latest` ranges.
- Dev dependencies separated from production.

### 10. Security
- Validate/sanitize all user input on the server.
- Parameterize all DB queries.
- Auto-escape templating; no `dangerouslySetInnerHTML` / `| safe`
  without lead approval.
- AuthN/AuthZ on every endpoint.
- HTTPS only (except `localhost`).
- Security headers: CSP, X-Content-Type-Options, HSTS, X-Frame-Options.
- CSRF protection (Django middleware / secure token storage on SPA).
- Rate-limit auth endpoints + public APIs.
- Never log passwords/tokens/PII.
- Principle of least privilege for service accounts.

### 11. Infrastructure
- `compose.yaml` (no `version:` key) for Docker Compose.

### 12. Enforcement
- Pre-commit hooks: format, lint, import order.
- CI: tests, lint, type check, build, dep audit.
- Code review: naming, docs, architecture, a11y.
- Non-compliance is grounds for requesting changes.

---
**When in doubt, fetch the latest version from Notion via the MCP server
and follow it — these guidelines evolve.**
