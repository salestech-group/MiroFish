# Commit Rules

Whenever committing, use the **Conventional Commits** standard.

## Format
```
<type>(<scope>): <short summary>

<optional body>

<optional footer>
```

## Types
- `feat` — A new feature
- `fix` — A bug fix
- `docs` — Documentation only changes
- `style` — Changes that do not affect meaning (whitespace, formatting)
- `refactor` — Code change that neither fixes a bug nor adds a feature
- `test` — Adding or correcting tests
- `chore` — Build process, tooling, configuration
- `ci` — CI / CD configuration changes
- `perf` — Performance improvement

## Rules
- **Type** is required and must be lowercase.
- **Summary** must be lowercase, in imperative mood, max 72 characters,
  no trailing period.
- **Body** (if present) explains *what* and *why*, not *how*.
- **Footer** can reference tickets (e.g., `Closes PROJ-1234`).
- **Never** add a `Co-Authored-By:` block (no Claude/AI watermarks).
- Avoid mixing unrelated changes in a single commit.
- Never commit secrets, credentials, or environment files.

## Examples
```
feat(auth): add two-factor authentication flow

Implements TOTP-based 2FA using the authenticator app.
Users can enable/disable 2FA from their security settings.

Closes PROJ-1234
```

```
fix(cart): prevent duplicate items on rapid clicks
```
