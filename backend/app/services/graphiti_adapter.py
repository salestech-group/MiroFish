"""
Graphiti Adapter — Drop-in replacement for the Zep Cloud client.

Exposes the same namespace as the Zep client so all consuming code
(graph_builder, zep_tools, zep_entity_reader, etc.) needs only a
one-line import swap:

    from .graphiti_adapter import GraphitiAdapter
    self.client = GraphitiAdapter()

Then all  self.client.graph.*  calls work unchanged.
"""

import asyncio
import threading
import uuid as _uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType, EntityNode
from graphiti_core.edges import EntityEdge
from graphiti_core.search.search_config import SearchConfig, SearchResults
from graphiti_core.search.search_config_recipes import (
    NODE_HYBRID_SEARCH_RRF,
    EDGE_HYBRID_SEARCH_RRF,
)
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient

from ..config import Config
from ..utils.logger import get_logger
from .ollama_reranker import OllamaReranker

logger = get_logger('mirofish.graphiti_adapter')


# ---------------------------------------------------------------------------
# Monkey-patches: defensive node_operations
#
# graphiti-core 0.11.6 indexes into per-call lists using ids produced by the
# LLM without bounds-checking. When a non-OpenAI backend (Qwen/GLM/Ollama)
# hallucinates an out-of-range id, add_episode raises IndexError mid-pipeline
# and the whole episode (plus the rest of the build) fails.
#
# Two sites are affected:
#   • resolve_extracted_nodes — indexes extracted_nodes[resolution_id]
#     (tracked upstream as getzep/graphiti#882)
#   • extract_nodes — indexes entity_types_context[entity_type_id]
#
# Both are patched here. The replacements preserve original semantics but
# skip / fall back on invalid ids (logging a warning) instead of raising.
# ---------------------------------------------------------------------------
_graphiti_patches_installed = False


def _install_graphiti_patches() -> None:
    global _graphiti_patches_installed
    if _graphiti_patches_installed:
        return

    from time import time as _time

    from graphiti_core import graphiti as _graphiti_mod
    from graphiti_core.utils.maintenance import node_operations as _node_ops
    from graphiti_core.helpers import semaphore_gather
    from graphiti_core.prompts import prompt_library
    from graphiti_core.prompts.dedupe_nodes import NodeResolutions
    from graphiti_core.prompts.extract_nodes import ExtractedEntities, ExtractedEntity
    from graphiti_core.search.search import search
    from graphiti_core.search.search_filters import SearchFilters
    from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
    from graphiti_core.search.search_config import SearchResults
    from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
    from graphiti_core.graphiti_types import GraphitiClients
    from graphiti_core.utils.datetime_utils import utc_now
    from pydantic import BaseModel

    async def _safe_resolve_extracted_nodes(
        clients,
        extracted_nodes,
        episode=None,
        previous_episodes=None,
        entity_types=None,
    ):
        llm_client = clients.llm_client

        search_results = await semaphore_gather(
            *[
                search(
                    clients=clients,
                    query=node.name,
                    group_ids=[node.group_id],
                    search_filter=SearchFilters(),
                    config=NODE_HYBRID_SEARCH_RRF,
                )
                for node in extracted_nodes
            ]
        )

        existing_nodes_lists = [result.nodes for result in search_results]
        entity_types_dict = entity_types if entity_types is not None else {}

        extracted_nodes_context = [
            {
                'id': i,
                'name': node.name,
                'entity_type': node.labels,
                'entity_type_description': (
                    entity_types_dict.get(
                        next((item for item in node.labels if item != 'Entity'), '')
                    ).__doc__
                    if entity_types_dict.get(
                        next((item for item in node.labels if item != 'Entity'), '')
                    )
                    else 'Default Entity Type'
                ),
                'duplication_candidates': [
                    {
                        **{
                            'idx': j,
                            'name': candidate.name,
                            'entity_types': candidate.labels,
                        },
                        **candidate.attributes,
                    }
                    for j, candidate in enumerate(existing_nodes_lists[i])
                ],
            }
            for i, node in enumerate(extracted_nodes)
        ]

        context = {
            'extracted_nodes': extracted_nodes_context,
            'episode_content': episode.content if episode is not None else '',
            'previous_episodes': [ep.content for ep in previous_episodes]
            if previous_episodes is not None
            else [],
        }

        llm_response = await llm_client.generate_response(
            prompt_library.dedupe_nodes.nodes(context),
            response_model=NodeResolutions,
        )

        node_resolutions = llm_response.get('entity_resolutions', [])

        n_extracted = len(extracted_nodes)
        resolved_by_index: dict[int, EntityNode] = {}
        uuid_map: dict[str, str] = {}

        for resolution in node_resolutions:
            resolution_id = resolution.get('id', -1)
            duplicate_idx = resolution.get('duplicate_idx', -1)

            if not (0 <= resolution_id < n_extracted):
                logger.warning(
                    "Skipping invalid LLM dedupe id %r "
                    "(valid range 0..%d, received %d resolutions for %d nodes)",
                    resolution_id, n_extracted - 1, len(node_resolutions), n_extracted,
                )
                continue

            extracted_node = extracted_nodes[resolution_id]
            candidates = existing_nodes_lists[resolution_id]
            resolved_node = (
                candidates[duplicate_idx]
                if 0 <= duplicate_idx < len(candidates)
                else extracted_node
            )

            new_name = resolution.get('name')
            if new_name:
                resolved_node.name = new_name

            resolved_by_index[resolution_id] = resolved_node
            uuid_map[extracted_node.uuid] = resolved_node.uuid

        # Any extracted node the LLM forgot: keep it as new (no dedup).
        # Preserves data instead of silently dropping it.
        resolved_nodes: list[EntityNode] = []
        for i, node in enumerate(extracted_nodes):
            if i in resolved_by_index:
                resolved_nodes.append(resolved_by_index[i])
            else:
                logger.warning(
                    "LLM dedupe returned no resolution for extracted node "
                    "id=%d name=%r — keeping as new node",
                    i, node.name,
                )
                resolved_nodes.append(node)
                uuid_map.setdefault(node.uuid, node.uuid)

        return resolved_nodes, uuid_map

    async def _safe_extract_nodes(
        clients,
        episode,
        previous_episodes,
        entity_types=None,
    ):
        llm_client = clients.llm_client
        start = _time()
        llm_response: dict = {}
        custom_prompt = ''
        entities_missed = True
        reflexion_iterations = 0

        entity_types_context = [
            {
                'entity_type_id': 0,
                'entity_type_name': 'Entity',
                'entity_type_description': (
                    'Default entity classification. Use this entity type if '
                    'the entity is not one of the other listed types.'
                ),
            }
        ]
        if entity_types is not None:
            entity_types_context += [
                {
                    'entity_type_id': i + 1,
                    'entity_type_name': type_name,
                    'entity_type_description': type_model.__doc__,
                }
                for i, (type_name, type_model) in enumerate(entity_types.items())
            ]

        context = {
            'episode_content': episode.content,
            'episode_timestamp': episode.valid_at.isoformat(),
            'previous_episodes': [ep.content for ep in previous_episodes],
            'custom_prompt': custom_prompt,
            'entity_types': entity_types_context,
            'source_description': episode.source_description,
        }

        extracted_entities: list = []

        max_iters = _node_ops.MAX_REFLEXION_ITERATIONS
        while entities_missed and reflexion_iterations <= max_iters:
            if episode.source == EpisodeType.message:
                llm_response = await llm_client.generate_response(
                    prompt_library.extract_nodes.extract_message(context),
                    response_model=ExtractedEntities,
                )
            elif episode.source == EpisodeType.text:
                llm_response = await llm_client.generate_response(
                    prompt_library.extract_nodes.extract_text(context),
                    response_model=ExtractedEntities,
                )
            elif episode.source == EpisodeType.json:
                llm_response = await llm_client.generate_response(
                    prompt_library.extract_nodes.extract_json(context),
                    response_model=ExtractedEntities,
                )

            extracted_entities = [
                ExtractedEntity(**raw_entity)
                for raw_entity in llm_response.get('extracted_entities', [])
            ]

            reflexion_iterations += 1
            if reflexion_iterations < max_iters:
                missing_entities = await _node_ops.extract_nodes_reflexion(
                    llm_client,
                    episode,
                    previous_episodes,
                    [entity.name for entity in extracted_entities],
                )

                entities_missed = len(missing_entities) != 0

                custom_prompt = 'Make sure that the following entities are extracted: '
                for entity in missing_entities:
                    custom_prompt += f'\n{entity},'

        filtered_extracted_entities = [
            entity for entity in extracted_entities if entity.name.strip()
        ]
        end = _time()
        logger.debug(
            'Extracted new nodes: %s in %f ms',
            filtered_extracted_entities, (end - start) * 1000,
        )

        n_types = len(entity_types_context)
        extracted_nodes: list[EntityNode] = []
        for extracted_entity in filtered_extracted_entities:
            entity_type_id = extracted_entity.entity_type_id
            if 0 <= entity_type_id < n_types:
                entity_type_name = entity_types_context[entity_type_id].get(
                    'entity_type_name'
                )
            else:
                logger.warning(
                    "LLM returned invalid entity_type_id=%r for entity %r "
                    "(valid range 0..%d) — falling back to 'Entity'",
                    entity_type_id, extracted_entity.name, n_types - 1,
                )
                entity_type_name = 'Entity'

            labels: list[str] = list({'Entity', str(entity_type_name)})

            new_node = EntityNode(
                name=extracted_entity.name,
                group_id=episode.group_id,
                labels=labels,
                summary='',
                created_at=utc_now(),
            )
            extracted_nodes.append(new_node)
            logger.debug('Created new node: %s (UUID: %s)', new_node.name, new_node.uuid)

        logger.debug(
            'Extracted nodes: %s',
            [(n.name, n.uuid) for n in extracted_nodes],
        )
        return extracted_nodes

    _node_ops.resolve_extracted_nodes = _safe_resolve_extracted_nodes
    _graphiti_mod.resolve_extracted_nodes = _safe_resolve_extracted_nodes
    _node_ops.extract_nodes = _safe_extract_nodes
    _graphiti_mod.extract_nodes = _safe_extract_nodes
    _graphiti_patches_installed = True
    logger.info(
        "Installed defensive node_operations patches "
        "(extract_nodes + resolve_extracted_nodes; work around graphiti-core "
        "IndexError; see getzep/graphiti#882)"
    )


_install_graphiti_patches()


class _PassthroughReranker(CrossEncoderClient):
    """Provider-agnostic no-op reranker.

    Returns passages in the order Graphiti supplied them with synthetic
    descending scores. Injected explicitly so Graphiti does not fall back
    to its default ``OpenAIRerankerClient`` (which uses a hard-coded
    ``gpt-4.1-nano`` model with logprobs and would 401 against Qwen /
    Dashscope keys). Selected when ``Config.RERANKER_PROVIDER == "none"``
    — useful for CI / slim containers that cannot pull the reranker model.
    For real reranking, set ``RERANKER_PROVIDER=ollama`` (the default).
    """

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]

# ---------------------------------------------------------------------------
# Persistent event loop in a dedicated background thread.
# All async calls are submitted here so the Neo4j driver (which is bound
# to one event loop) never crosses loop boundaries.
# ---------------------------------------------------------------------------
_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_loop_lock = threading.Lock()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop is None:
        with _loop_lock:
            if _loop is None:
                _loop = asyncio.new_event_loop()
                _loop_thread = threading.Thread(
                    target=_loop.run_forever, daemon=True, name="graphiti-event-loop"
                )
                _loop_thread.start()
    return _loop


def _run(coro):
    """Submit coroutine to the persistent event loop thread and wait for result."""
    future = asyncio.run_coroutine_threadsafe(coro, _get_loop())
    return future.result(timeout=1800)


# ---------------------------------------------------------------------------
# Singleton Graphiti instance (one Neo4j driver for the whole process)
# ---------------------------------------------------------------------------
_graphiti_instance: Optional[Graphiti] = None
_graphiti_lock = threading.Lock()


_ALLOWED_GRAPHITI_PROVIDERS = ("openai", "gemini")
_ALLOWED_RERANKER_PROVIDERS = ("ollama", "none")


def _build_reranker(provider: str) -> CrossEncoderClient:
    """Build the cross-encoder reranker for the configured provider.

    Defers to ``_PassthroughReranker`` when ``provider`` is ``"none"``
    (the legacy no-op behaviour, useful for CI / slim containers that
    cannot pull the reranker model). For ``"ollama"`` it constructs the
    real Ollama-backed reranker; the construction is side-effect-free, so
    Graphiti initialisation does not depend on the Ollama daemon being
    reachable at startup.
    """
    if provider == "none":
        return _PassthroughReranker()
    if provider == "ollama":
        return OllamaReranker(
            model=Config.RERANKER_MODEL,
            base_url=Config.RERANKER_BASE_URL,
            api_key=Config.RERANKER_API_KEY,
        )
    raise ValueError(
        f"Unknown RERANKER_PROVIDER={provider!r}; "
        f"allowed: {_ALLOWED_RERANKER_PROVIDERS}"
    )


def _build_llm_and_embedder(provider: str):
    """Build (llm_client, embedder) for the requested Graphiti provider.

    Lazy-imports provider-specific Graphiti classes so a missing optional
    dependency for one provider does not break the other at import time.
    """
    if provider == "openai":
        from graphiti_core.llm_client.openai_client import OpenAIClient
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

        llm_client = OpenAIClient(
            config=LLMConfig(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
                model=Config.LLM_MODEL_NAME,
                small_model=Config.LLM_SMALL_MODEL_NAME,
            )
        )
        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=Config.EMBEDDING_API_KEY or Config.LLM_API_KEY,
                base_url=Config.EMBEDDING_BASE_URL or Config.LLM_BASE_URL,
                embedding_model=Config.EMBEDDING_MODEL,
            )
        )
        return llm_client, embedder

    if provider == "gemini":
        from graphiti_core.llm_client.gemini_client import GeminiClient
        from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig

        llm_client = GeminiClient(
            config=LLMConfig(
                api_key=Config.LLM_API_KEY,
                model=Config.LLM_MODEL_NAME,
            )
        )
        embedder = GeminiEmbedder(
            config=GeminiEmbedderConfig(
                api_key=Config.LLM_API_KEY,
                embedding_model=Config.EMBEDDING_MODEL,
            )
        )
        return llm_client, embedder

    raise ValueError(
        f"Unknown GRAPHITI_LLM_PROVIDER={provider!r}; "
        f"allowed: {_ALLOWED_GRAPHITI_PROVIDERS}"
    )


def _get_graphiti() -> Graphiti:
    global _graphiti_instance
    if _graphiti_instance is None:
        with _graphiti_lock:
            if _graphiti_instance is None:
                provider = (Config.GRAPHITI_LLM_PROVIDER or "openai").lower()
                logger.info(f"Initializing Graphiti client (provider={provider})...")
                reranker_provider = (Config.RERANKER_PROVIDER or "ollama").lower()
                logger.info(
                    f"Initializing Graphiti reranker (provider={reranker_provider})..."
                )
                llm_client, embedder = _build_llm_and_embedder(provider)
                cross_encoder = _build_reranker(reranker_provider)
                g = Graphiti(
                    Config.NEO4J_URI,
                    Config.NEO4J_USER,
                    Config.NEO4J_PASSWORD,
                    llm_client=llm_client,
                    embedder=embedder,
                    cross_encoder=cross_encoder,
                )
                # Use the persistent loop so the driver is bound to it from the start
                _run(g.build_indices_and_constraints())
                _graphiti_instance = g
                logger.info("Graphiti client ready.")
    return _graphiti_instance


# ---------------------------------------------------------------------------
# Compatibility data classes (mimic Zep response objects)
# ---------------------------------------------------------------------------

@dataclass
class _NodeResult:
    """Zep-compatible node object."""
    uuid_: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    created_at: Optional[str] = None

    @property
    def uuid(self):
        return self.uuid_


@dataclass
class _EdgeResult:
    """Zep-compatible edge object."""
    uuid_: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    attributes: Dict[str, Any]
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None

    @property
    def uuid(self):
        return self.uuid_


@dataclass
class _EpisodeResult:
    """Zep-compatible episode object — always processed (Graphiti is sync)."""
    uuid_: str
    processed: bool = True

    @property
    def uuid(self):
        return self.uuid_


@dataclass
class _SearchResults:
    """Zep-compatible search result object."""
    edges: List[_EdgeResult] = field(default_factory=list)
    nodes: List[_NodeResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers: convert Graphiti objects → Zep-compatible objects
# ---------------------------------------------------------------------------

def _to_ts(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat()


def _entity_node_to_result(n: EntityNode) -> _NodeResult:
    return _NodeResult(
        uuid_=n.uuid,
        name=n.name,
        labels=list(n.labels) if n.labels else ["Entity"],
        summary=n.summary or "",
        attributes=n.attributes or {},
        created_at=_to_ts(n.created_at),
    )


def _entity_edge_to_result(e: EntityEdge) -> _EdgeResult:
    return _EdgeResult(
        uuid_=e.uuid,
        name=e.name or "",
        fact=e.fact or "",
        source_node_uuid=e.source_node_uuid,
        target_node_uuid=e.target_node_uuid,
        attributes={},
        created_at=_to_ts(e.created_at),
        valid_at=_to_ts(e.valid_at),
        invalid_at=_to_ts(e.invalid_at),
        expired_at=_to_ts(e.expired_at),
    )


def _neo4j_record_to_node(record: Dict) -> _NodeResult:
    labels = record.get("labels", ["Entity"])
    if isinstance(labels, (list, tuple)):
        labels = [str(l) for l in labels]
    return _NodeResult(
        uuid_=record.get("uuid", ""),
        name=record.get("name", ""),
        labels=labels,
        summary=record.get("summary", ""),
        attributes=record.get("attributes") or {},
        created_at=str(record.get("created_at", "")) or None,
    )


def _neo4j_record_to_edge(record: Dict) -> _EdgeResult:
    def ts(v):
        return str(v) if v else None
    return _EdgeResult(
        uuid_=record.get("uuid", ""),
        name=record.get("name", ""),
        fact=record.get("fact", ""),
        source_node_uuid=record.get("source_node_uuid", ""),
        target_node_uuid=record.get("target_node_uuid", ""),
        attributes=record.get("attributes") or {},
        created_at=ts(record.get("created_at")),
        valid_at=ts(record.get("valid_at")),
        invalid_at=ts(record.get("invalid_at")),
        expired_at=ts(record.get("expired_at")),
    )


# ---------------------------------------------------------------------------
# Neo4j direct query helpers
# ---------------------------------------------------------------------------

async def _neo4j_query(graphiti: Graphiti, cypher: str, params: Dict) -> List[Dict]:
    """Execute a read Cypher query and return list of record dicts."""
    records, _, _ = await graphiti.driver.execute_query(cypher, params)
    return [dict(r) for r in records]


async def _neo4j_write(graphiti: Graphiti, cypher: str, params: Dict) -> None:
    """Execute a write Cypher query."""
    await graphiti.driver.execute_query(cypher, params)


# Cypher queries
_NODES_BY_GROUP = """
MATCH (n:Entity {group_id: $group_id})
RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
       labels(n) AS labels, n.created_at AS created_at,
       n.attributes AS attributes
ORDER BY n.created_at ASC
SKIP $skip LIMIT $limit
"""

_EDGES_BY_GROUP = """
MATCH (s:Entity {group_id: $group_id})-[r:RELATES_TO]->(t:Entity {group_id: $group_id})
RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
       s.uuid AS source_node_uuid,
       t.uuid AS target_node_uuid,
       r.created_at AS created_at, r.valid_at AS valid_at,
       r.invalid_at AS invalid_at, r.expired_at AS expired_at,
       r.attributes AS attributes
ORDER BY r.created_at ASC
SKIP $skip LIMIT $limit
"""

_NODE_BY_UUID = """
MATCH (n:Entity {uuid: $uuid})
RETURN n.uuid AS uuid, n.name AS name, n.summary AS summary,
       labels(n) AS labels, n.created_at AS created_at,
       n.group_id AS group_id, n.attributes AS attributes
LIMIT 1
"""

_EDGES_BY_NODE_UUID = """
MATCH (s:Entity {uuid: $node_uuid})-[r:RELATES_TO]->(t:Entity)
RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
       s.uuid AS source_node_uuid,
       t.uuid AS target_node_uuid,
       r.created_at AS created_at, r.valid_at AS valid_at,
       r.invalid_at AS invalid_at, r.expired_at AS expired_at
UNION
MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity {uuid: $node_uuid})
RETURN r.uuid AS uuid, r.name AS name, r.fact AS fact,
       s.uuid AS source_node_uuid,
       t.uuid AS target_node_uuid,
       r.created_at AS created_at, r.valid_at AS valid_at,
       r.invalid_at AS invalid_at, r.expired_at AS expired_at
"""

_DELETE_GROUP = """
MATCH (n:Entity {group_id: $group_id})
DETACH DELETE n
"""


# ---------------------------------------------------------------------------
# Sub-namespaces
# ---------------------------------------------------------------------------

class _EpisodeNamespace:
    def get(self, uuid_: str) -> _EpisodeResult:
        """Always returns processed=True — Graphiti is synchronous."""
        return _EpisodeResult(uuid_=uuid_, processed=True)


class _NodeNamespace:
    def __init__(self, graphiti: Graphiti):
        self._g = graphiti

    def get_by_graph_id(
        self,
        graph_id: str,
        limit: int = 100,
        uuid_cursor: Optional[str] = None,
    ) -> List[_NodeResult]:
        """Return nodes for a group. First call returns all; cursor call returns empty."""
        if uuid_cursor is not None:
            # Already fetched all on first call — signal end of pagination
            return []
        records = _run(_neo4j_query(
            self._g, _NODES_BY_GROUP,
            {"group_id": graph_id, "skip": 0, "limit": 10000}
        ))
        return [_neo4j_record_to_node(r) for r in records]

    def get(self, uuid_: str) -> _NodeResult:
        records = _run(_neo4j_query(self._g, _NODE_BY_UUID, {"uuid": uuid_}))
        if not records:
            return _NodeResult(uuid_=uuid_, name="", labels=[], summary="", attributes={})
        return _neo4j_record_to_node(records[0])

    def get_entity_edges(self, node_uuid: str) -> List[_EdgeResult]:
        records = _run(_neo4j_query(
            self._g, _EDGES_BY_NODE_UUID, {"node_uuid": node_uuid}
        ))
        return [_neo4j_record_to_edge(r) for r in records]


class _EdgeNamespace:
    def __init__(self, graphiti: Graphiti):
        self._g = graphiti

    def get_by_graph_id(
        self,
        graph_id: str,
        limit: int = 100,
        uuid_cursor: Optional[str] = None,
    ) -> List[_EdgeResult]:
        """Return edges for a group. First call returns all; cursor call returns empty."""
        if uuid_cursor is not None:
            return []
        records = _run(_neo4j_query(
            self._g, _EDGES_BY_GROUP,
            {"group_id": graph_id, "skip": 0, "limit": 50000}
        ))
        return [_neo4j_record_to_edge(r) for r in records]


class _GraphNamespace:
    def __init__(self, graphiti: Graphiti):
        self._g = graphiti
        self.node = _NodeNamespace(graphiti)
        self.edge = _EdgeNamespace(graphiti)
        self.episode = _EpisodeNamespace()
        self._ontologies: Dict[str, Dict] = {}  # graph_id -> ontology dict

    def create(self, graph_id: str, name: str, description: str = "") -> None:
        """No-op — Graphiti uses group_id implicitly, no explicit creation needed."""
        logger.info(f"Graph '{graph_id}' registered (group_id in Graphiti)")

    def set_ontology(
        self,
        graph_ids: List[str],
        entities: Any = None,
        edges: Any = None,
    ) -> None:
        """Store ontology hints for use during episode ingestion. Graphiti extracts entities dynamically."""
        for gid in graph_ids:
            self._ontologies[gid] = {"entities": entities, "edges": edges}
        logger.info(f"Ontology hints stored for graphs: {graph_ids}")

    def add(self, graph_id: str, type: str = "text", data: str = "") -> _EpisodeResult:
        """Add a single text episode to the graph."""
        result = _run(self._g.add_episode(
            name=f"activity_{_uuid_mod.uuid4().hex[:8]}",
            episode_body=data,
            source_description="MiroFish simulation activity",
            reference_time=datetime.now(timezone.utc),
            source=EpisodeType.text,
            group_id=graph_id,
            update_communities=False,
        ))
        ep_uuid_out = result.episode.uuid if result and result.episode else str(_uuid_mod.uuid4())
        return _EpisodeResult(uuid_=ep_uuid_out)

    def add_batch(self, graph_id: str, episodes: List[Any]) -> List[_EpisodeResult]:
        """Add a batch of episodes. Returns one _EpisodeResult per episode in input order.

        On the first ingestion failure the underlying exception is logged at ERROR
        level (with traceback) and re-raised; episodes successfully ingested before
        the failure remain committed in Neo4j. The caller (the graph-build worker)
        translates the propagated exception into Task.status = FAILED with the
        underlying error message — never substitute a placeholder UUID, since that
        would produce a Task that looks completed while the graph is empty.
        """
        results = []
        for index, ep in enumerate(episodes):
            text = getattr(ep, 'data', '') or str(ep)
            try:
                result = _run(self._g.add_episode(
                    name=f"chunk_{_uuid_mod.uuid4().hex[:8]}",
                    episode_body=text,
                    source_description="MiroFish document chunk",
                    reference_time=datetime.now(timezone.utc),
                    source=EpisodeType.text,
                    group_id=graph_id,
                    update_communities=False,
                ))
            except Exception:
                logger.exception(
                    "Episode add failed (group_id=%s, episode_index=%d)",
                    graph_id, index,
                )
                raise
            ep_uuid_out = result.episode.uuid if result and result.episode else str(_uuid_mod.uuid4())
            results.append(_EpisodeResult(uuid_=ep_uuid_out))
        return results

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ) -> _SearchResults:
        """Semantic search over the graph. scope='edges'|'nodes'|'both'."""
        try:
            if scope == "nodes":
                results = _run(self._g.search_(
                    query=query,
                    config=SearchConfig(
                        node_config=NODE_HYBRID_SEARCH_RRF.node_config,
                        limit=limit,
                    ),
                    group_ids=[graph_id],
                ))
                nodes = [_entity_node_to_result(n) for n in (results.nodes or [])]
                return _SearchResults(nodes=nodes)
            else:
                edges = _run(self._g.search(
                    query=query,
                    group_ids=[graph_id],
                    num_results=limit,
                ))
                return _SearchResults(edges=[_entity_edge_to_result(e) for e in (edges or [])])
        except Exception as e:
            logger.warning(f"Graph search failed: {str(e)[:150]}")
            return _SearchResults()

    def delete(self, graph_id: str) -> None:
        """Delete all nodes and edges for a group_id."""
        _run(_neo4j_write(self._g, _DELETE_GROUP, {"group_id": graph_id}))
        logger.info(f"Graph '{graph_id}' deleted from Neo4j")


# ---------------------------------------------------------------------------
# Main adapter class — drop-in for  Zep(api_key=...)
# ---------------------------------------------------------------------------

class GraphitiAdapter:
    """
    Drop-in replacement for  `from zep_cloud.client import Zep`.

    Usage:
        self.client = GraphitiAdapter()
        self.client.graph.create(graph_id, name)
        self.client.graph.search(graph_id, query, limit, scope)
        self.client.graph.node.get(uuid_)
        ...
    """

    def __init__(self, api_key: Optional[str] = None):
        # api_key ignored — kept for signature compatibility
        graphiti = _get_graphiti()
        self.graph = _GraphNamespace(graphiti)
