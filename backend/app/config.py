"""Configuration management.

Loads configuration values from the project-root ``.env`` file.
"""

import os
from dotenv import load_dotenv

# Load the project-root .env file.
# Path: MiroFish/.env (relative to backend/app/config.py).
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If the project root has no .env, fall back to the process environment
    # (used in production deployments).
    load_dotenv(override=True)


class Config:
    """Flask configuration class."""

    # Flask settings.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON settings: disable ASCII escaping so non-ASCII output renders literally
    # rather than as \uXXXX escape sequences.
    JSON_AS_ASCII = False

    # LLM settings (called via the OpenAI-compatible API surface).
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Neo4j + Graphiti settings (knowledge-graph store).
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'mirofish123')
    # Embedding pipeline — defaults target a local Ollama instance running
    # `mxbai-embed-large` (1024-dim, matches Graphiti's vector index). Override
    # any of the three EMBEDDING_* env vars to point at OpenAI, Gemini, or any
    # other OpenAI-SDK-compatible endpoint. See `.env.example` for snippets.
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'mxbai-embed-large')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434/v1')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY', 'ollama')

    # Graphiti provider switch. Allowed: "openai", "gemini".
    # "openai" works for any OpenAI-SDK-compatible endpoint (Ollama via its
    # /v1 surface, Qwen via Dashscope, GLM, OpenAI itself). Set to "gemini"
    # to use Google Gemini directly.
    GRAPHITI_LLM_PROVIDER = os.environ.get('GRAPHITI_LLM_PROVIDER', 'openai')

    # Reranker (cross-encoder) settings. The reranker reorders Graphiti search
    # results before they reach the ReportAgent tools. Defaults target the same
    # local Ollama host used for embeddings; setting RERANKER_PROVIDER=none
    # disables reranking and keeps the legacy passthrough (useful for CI or
    # slim containers that cannot pull the reranker model). RERANKER_BASE_URL
    # and RERANKER_API_KEY chain through EMBEDDING_BASE_URL / EMBEDDING_API_KEY
    # so a single-host Ollama deployment needs no extra configuration.
    RERANKER_PROVIDER = os.environ.get('RERANKER_PROVIDER', 'ollama')
    RERANKER_MODEL = os.environ.get('RERANKER_MODEL', 'qwen2.5:3b')
    RERANKER_BASE_URL = os.environ.get(
        'RERANKER_BASE_URL',
        os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434/v1'),
    )
    RERANKER_API_KEY = os.environ.get(
        'RERANKER_API_KEY',
        os.environ.get('EMBEDDING_API_KEY', 'ollama'),
    )

    # File upload settings.
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing settings.
    DEFAULT_CHUNK_SIZE = 500  # default chunk size in characters
    DEFAULT_CHUNK_OVERLAP = 50  # default overlap in characters

    # OASIS simulation settings.
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS per-platform allowed action lists.
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report agent settings.
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    @classmethod
    def validate(cls):
        """Validate that required configuration values are present."""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_PASSWORD 未配置")
        return errors

