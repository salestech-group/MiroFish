# Handoff — graphiti-ollama-reranker

## What shipped

| Task | Status | Notes |
|------|--------|-------|
| 1.1 — Config knobs | ✅ | Four `RERANKER_*` attrs added; `BASE_URL`/`API_KEY` chain to `EMBEDDING_*`. |
| 2.1 — `OllamaReranker` | ✅ | New `backend/app/services/ollama_reranker.py`. Construction is side-effect-free; `rank()` never raises; per-passage parse falls back to deterministic low score; whole-call failure degrades to passthrough order with a single WARNING log. |
| 3.1 — Factory wiring | ✅ | `_get_graphiti()` selects the reranker via new `_build_reranker()`. INFO log announces selection. `ValueError` raised for unknown providers. |
| 4.1 — `.env.example` | ⚠️ Deferred | The `pre_tool_env_guard.sh` Claude hook blocks all `.env*` access (Read, Write, Edit, Bash). Cannot be performed inside this autonomous sandbox. **Reviewer action required** — see snippet below. |
| 4.2 — `CLAUDE.md` | ✅ | New `RERANKER_*` block added under "Required Environment Variables". |
| 4.3 — `README.md` | ✅ | Adds `ollama pull qwen2.5:3b` to the prerequisites and a `RERANKER_*` block in the `.env` snippet. `README-EN.md` / `README-ZH.md` left out per design scope (i18n is its own workstream). |
| 4.4 — Prior-spec follow-up note | ✅ | Updated `graphiti-neo4j-finalize`'s `research.md`, `design.md`, and `HANDOFF.md` to point at this spec; updated the `_PassthroughReranker` docstring in `graphiti_adapter.py`. |
| 5.1 — Structural sweep | ✅ | `gpt-4.1-nano` / `OpenAIRerankerClient` referenced only in docstring text. `OllamaReranker` has exactly one import + one use site. `_GraphNamespace.search` still filters by `group_id`. |

## Reviewer action required: `.env.example`

Please paste the following block into `.env.example` alongside the existing `EMBEDDING_*` section:

```env
# Reranker — reorders Graphiti search results before the report tools see them.
# Default targets the same local Ollama host used for embeddings.
# Pre-requisite for the default: `ollama pull qwen2.5:3b`.
# Set RERANKER_PROVIDER=none to keep the legacy passthrough (useful for CI /
# slim containers that cannot pull a reranker model).
RERANKER_PROVIDER=ollama
RERANKER_MODEL=qwen2.5:3b
# Optional — both default to the EMBEDDING_* equivalents when unset.
# RERANKER_BASE_URL=http://localhost:11434/v1
# RERANKER_API_KEY=ollama
```

This block matches what `CLAUDE.md` and `README.md` document. After paste, R6.1 is satisfied and ticket #39's acceptance-criteria checkbox "Configuration is overridable via env vars and documented in `.env.example`" becomes green.

## Verification performed

- `Config` loads with the documented defaults; `EMBEDDING_BASE_URL` override propagates to `RERANKER_BASE_URL`.
- `OllamaReranker` constructs without network I/O; empty `passages` returns `[]`; whole-call failure logs WARNING and returns passthrough-ordered tuples.
- `_build_reranker("ollama")` → `OllamaReranker`; `("none")` → `_PassthroughReranker`; `("banana")` → `ValueError` naming the offender and listing `("ollama", "none")`.
- Grep sweep matches design expectations (see Tasks 5.1 in `tasks.md`).

## Smoke test (recommended before merge)

With Ollama running and the reranker model pulled:

```bash
ollama pull qwen2.5:3b
RERANKER_PROVIDER=ollama npm run backend
# In another shell, exercise a graph build + report tool and confirm:
#   - Startup log shows "Initializing Graphiti reranker (provider=ollama)..."
#   - Search-backed report tool results differ from `RERANKER_PROVIDER=none` output
#   - No WARNING about reranker failure in `backend/logs/`
```
