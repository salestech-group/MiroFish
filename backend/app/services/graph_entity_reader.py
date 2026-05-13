"""Graph entity reader and filter service.

Reads nodes from the knowledge graph and filters down to those that match
a predefined ontology of entity types.
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from .graphiti_adapter import GraphitiAdapter

from ..config import Config
from ..utils.logger import get_logger
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from ..utils.locale import t

logger = get_logger('mirofish.graph_entity_reader')

# Generic return-type variable.
T = TypeVar('T')


@dataclass
class EntityNode:
    """In-memory representation of an entity node from the graph."""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Edges connected to this entity.
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Other nodes connected through related edges.
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """Return the first non-default label, or ``None`` if only defaults are present."""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Result of a filter pass over the graph: matching entities + counts."""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class GraphEntityReader:
    """Read entities from the knowledge graph and filter to ontology-defined types.

    Capabilities:
    1. Read all nodes from the graph.
    2. Keep nodes whose labels include something other than the default ``Entity``.
    3. Optionally enrich each entity with its connected edges and neighboring nodes.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = GraphitiAdapter()

    def _call_with_retry(
        self,
        func: Callable[[], T],
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """Call a graph API function with retry on failure.

        Args:
            func: A zero-argument callable performing the request.
            operation_name: Operation label used in log output.
            max_retries: Maximum number of attempts (default 3 — i.e. up to 3 tries total).
            initial_delay: Initial delay between retries in seconds.

        Returns:
            The return value of ``func``.
        """
        last_exception = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        t("log.graph_entity_reader.m001", operation_name=operation_name, attempt=attempt + 1, str=str(e)[:100], delay=delay)
                    )
                    time.sleep(delay)
                    delay *= 2  # exponential backoff
                else:
                    logger.error(t("log.graph_entity_reader.m002", operation_name=operation_name, max_retries=max_retries, str=str(e)))

        raise last_exception

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return every node in the graph (paginated under the hood).

        Args:
            graph_id: Graph identifier.

        Returns:
            A list of node dicts.
        """
        logger.info(t("log.graph_entity_reader.m003", graph_id=graph_id))

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(t("log.graph_entity_reader.m004", len=len(nodes_data)))
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """Return every edge in the graph (paginated under the hood).

        Args:
            graph_id: Graph identifier.

        Returns:
            A list of edge dicts.
        """
        logger.info(t("log.graph_entity_reader.m005", graph_id=graph_id))

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(t("log.graph_entity_reader.m006", len=len(edges_data)))
        return edges_data

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """Return every edge connected to the given node (with retry).

        Args:
            node_uuid: Node UUID.

        Returns:
            A list of edge dicts.
        """
        try:
            # Wrap the API call in retry logic.
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"获取节点边(node={node_uuid[:8]}...)"
            )

            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })

            return edges_data
        except Exception as e:
            logger.warning(t("log.graph_entity_reader.m007", node_uuid=node_uuid, str=str(e)))
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """Filter nodes down to entities matching the predefined ontology types.

        Filtering rules:
        - Skip nodes whose only label is ``Entity`` (uncategorized).
        - Keep nodes whose labels include anything other than ``Entity`` and ``Node``.

        Args:
            graph_id: Graph identifier.
            defined_entity_types: Optional allow-list; when provided, only matching types are kept.
            enrich_with_edges: When ``True``, populate related_edges and related_nodes.

        Returns:
            A ``FilteredEntities`` summary.
        """
        logger.info(t("log.graph_entity_reader.m008", graph_id=graph_id))

        # Look up ontology from project to classify entities
        ontology = None
        try:
            from ..models.project import ProjectManager
            from .graph_builder import _classify_entity_type
            for p in ProjectManager.list_projects():
                if p.graph_id == graph_id and p.ontology:
                    ontology = p.ontology
                    break
        except Exception:
            pass

        # Read every node from the graph.
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        # Apply ontology-based classification so all nodes get proper type labels
        if ontology:
            for node in all_nodes:
                labels = node.get("labels", [])
                custom = [l for l in labels if l not in ("Entity", "Node")]
                if not custom:
                    entity_type = _classify_entity_type(
                        node.get("name", ""), node.get("summary", ""), ontology
                    )
                    if entity_type != "Entity":
                        node["labels"] = [entity_type] + labels

        # Read every edge so we can enrich entities later.
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        # uuid -> node-data map for fast lookup.
        node_map = {n["uuid"]: n for n in all_nodes}

        # Filter to entities that match the criteria.
        filtered_entities = []
        entity_types_found = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            # Filtering rule: labels must contain something other than the defaults.
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]

            if not custom_labels:
                # Only default labels — skip.
                continue

            # When a predefined-type list is supplied, require a match against it.
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )

            # Enrich with related edges and neighboring nodes.
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                # Populate basic info for each neighboring node.
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(t("log.graph_entity_reader.m009", total_count=total_count, len=len(filtered_entities), entity_types_found=entity_types_found))

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """Fetch a single entity with its full context (edges + neighbors), with retry.

        Args:
            graph_id: Graph identifier.
            entity_uuid: Entity UUID.

        Returns:
            ``EntityNode`` or ``None`` if not found.
        """
        try:
            # Fetch the node with retry.
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"获取节点详情(uuid={entity_uuid[:8]}...)"
            )

            if not node:
                return None

            # Edges connected to this node.
            edges = self.get_node_edges(entity_uuid)

            # All graph nodes, used for neighbor lookup.
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}

            # Collect related edges and neighboring uuids.
            related_edges = []
            related_node_uuids = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            # Populate basic info for each neighboring node.
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })

            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            logger.error(t("log.graph_entity_reader.m010", entity_uuid=entity_uuid, str=str(e)))
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """Return every entity matching the given type.

        Args:
            graph_id: Graph identifier.
            entity_type: Entity type label (e.g. ``Student``, ``PublicFigure``).
            enrich_with_edges: When ``True``, populate related edges/nodes.

        Returns:
            A list of matching ``EntityNode`` instances.
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


