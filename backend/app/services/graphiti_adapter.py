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
from graphiti_core.llm_client.gemini_client import GeminiClient
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.graphiti_adapter')


class _GeminiReranker(CrossEncoderClient):
    """Simple reranker using Gemini — returns passages sorted by relevance."""

    def __init__(self, client: GeminiClient):
        self._client = client

    async def rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        if not passages:
            return []
        # Return in original order — Gemini doesn't support logprobs for reranking
        # This is a no-op reranker: correct but unoptimized ordering
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
    return future.result(timeout=300)


# ---------------------------------------------------------------------------
# Singleton Graphiti instance (one Neo4j driver for the whole process)
# ---------------------------------------------------------------------------
_graphiti_instance: Optional[Graphiti] = None
_graphiti_lock = threading.Lock()


def _get_graphiti() -> Graphiti:
    global _graphiti_instance
    if _graphiti_instance is None:
        with _graphiti_lock:
            if _graphiti_instance is None:
                logger.info("Initializing Graphiti client...")
                llm_cfg = LLMConfig(
                    api_key=Config.LLM_API_KEY,
                    model=Config.LLM_MODEL_NAME,
                )
                llm_client = GeminiClient(config=llm_cfg)
                embedder = GeminiEmbedder(
                    config=GeminiEmbedderConfig(
                        api_key=Config.LLM_API_KEY,
                        embedding_model=Config.EMBEDDING_MODEL,
                    )
                )
                cross_encoder = _GeminiReranker(llm_client)
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
        """Add a batch of episodes. Returns list of EpisodeResult with uuid_."""
        results = []
        for ep in episodes:
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
                ep_uuid_out = result.episode.uuid if result and result.episode else str(_uuid_mod.uuid4())
            except Exception as e:
                logger.warning(f"Episode add failed: {str(e)[:100]}, using placeholder uuid")
                ep_uuid_out = str(_uuid_mod.uuid4())
            results.append(_EpisodeResult(uuid_=ep_uuid_out))
        return results

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
        reranker: Optional[str] = None,
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
