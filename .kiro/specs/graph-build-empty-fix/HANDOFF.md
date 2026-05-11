# Handoff: `.env.example` Update Required Before Merge

The Claude harness cannot write `.env.example` (the path is protected by the
`pre_tool_env_guard.sh` hook). Apply the following change manually before
merging this branch.

## What to change

`.env.example` currently presents the local-Ollama embedder block as a
commented-out option. After this change it must present the same block
*uncommented* (as the active default), with OpenAI and Gemini examples
preserved beneath as commented fallback blocks.

This must line up with `backend/app/config.py`'s new defaults
(`mxbai-embed-large`, `http://localhost:11434/v1`, `ollama`) so that
operators copying `.env.example` to `.env` see the same values the backend
falls back to when those keys are unset.

## Required block

Replace whatever currently lives in `.env.example`'s "Embedding" section
with the block below. Keep the surrounding sections (LLM, Neo4j, optional
LLM_BOOST, ZEP_API_KEY) untouched.

```env
# Embeddings — default: local Ollama, free, no API key, OpenAI-compatible
# endpoint. Pre-requisite: `ollama pull mxbai-embed-large` (1024-dim, matches
# Graphiti). In Docker, the container reaches the host daemon via
# host.docker.internal:11434 (see docker-compose.yml); in host mode
# (`npm run dev`), keep http://localhost:11434/v1 as below.
EMBEDDING_BASE_URL=http://localhost:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=mxbai-embed-large

# Embeddings — remote fallback (uncomment ONE block if you prefer not to run
# Ollama locally). Note: any override must produce 1024-dim vectors to match
# Graphiti's vector index — 768-dim models (e.g. nomic-embed-text) are NOT
# supported.
#
# OpenAI:
# EMBEDDING_BASE_URL=https://api.openai.com/v1
# EMBEDDING_API_KEY=your_openai_api_key
# EMBEDDING_MODEL=text-embedding-3-small
#
# Gemini (also set GRAPHITI_LLM_PROVIDER=gemini):
# EMBEDDING_MODEL=gemini-embedding-001
```

## Consistency check

After applying, confirm:

- `EMBEDDING_MODEL=mxbai-embed-large` matches
  `Config.EMBEDDING_MODEL` default in `backend/app/config.py`.
- `EMBEDDING_BASE_URL=http://localhost:11434/v1` matches
  `Config.EMBEDDING_BASE_URL` default.
- `EMBEDDING_API_KEY=ollama` matches `Config.EMBEDDING_API_KEY` default.
- The README's env block (the one inside `README.md`) shows the same
  uncommented default values and the same commented OpenAI/Gemini
  fallbacks.

## Why this is not auto-applied

`.env.example` lives in the project root and matches the
`pre_tool_env_guard.sh` blocklist for env / secrets paths. The guard is
deliberately broad (any `.env*` filename) to prevent accidental writes to
real secret files. The fix is one-line manual application; do not weaken
the guard.
