"""Graph build service.

Pipeline step 2: build the project's standalone knowledge graph through the
Graphiti API.
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .graphiti_adapter import GraphitiAdapter

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.graph_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor
from ..utils.locale import t, get_locale, set_locale
from ..utils.logger import get_logger

logger = get_logger('mirofish.graph_builder')


def _classify_entity_type(name: str, summary: str, ontology: Optional[Dict]) -> str:
    """
    Classify an entity into an ontology type using keyword matching
    against entity type names, descriptions, and examples.
    Falls back to 'Entity' if no ontology or no match found.
    """
    if not ontology:
        return "Entity"
    entity_types = ontology.get("entity_types", [])
    if not entity_types:
        return "Entity"

    name_lower = (name or "").lower()
    summary_lower = (summary or "").lower()
    search_text = f"{name_lower} {summary_lower}"

    best_type = "Entity"
    best_score = 0

    for et in entity_types:
        score = 0
        type_name = et.get("name", "")
        type_name_lower = type_name.lower()

        # Exact name match in type name
        if type_name_lower in name_lower:
            score += 10

        # Check examples list
        for example in et.get("examples", []):
            if example.lower() in search_text:
                score += 8
            elif name_lower in example.lower():
                score += 6

        # Check description keywords
        desc_words = (et.get("description", "")).lower().split()
        for word in desc_words:
            if len(word) > 4 and word in search_text:
                score += 1

        if score > best_score:
            best_score = score
            best_type = type_name

    return best_type if best_score > 0 else "Entity"


@dataclass
class GraphInfo:
    """Summary information about a built graph."""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """Drives knowledge-graph construction via the Graphiti API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.client = GraphitiAdapter()
        self.task_manager = TaskManager()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """Kick off a graph build asynchronously.

        Args:
            text: Source text to ingest.
            ontology: Ontology definition (the output of pipeline step 1).
            graph_name: Display name for the graph.
            chunk_size: Characters per text chunk.
            chunk_overlap: Overlap (in characters) between consecutive chunks.
            batch_size: Number of chunks pushed to Graphiti per batch.

        Returns:
            The id of the task tracking the build.
        """
        # Register a task to track build progress.
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # Capture locale before spawning background thread
        current_locale = get_locale()

        # Run the build on a background thread so the request returns immediately.
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size, current_locale)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
        locale: str = 'zh'
    ):
        """Background worker that performs the graph build."""
        set_locale(locale)
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message=t('progress.startBuildingGraph')
            )
            
            # 1. Create the graph.
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=t('progress.graphCreated', graphId=graph_id)
            )
            
            # 2. Set the ontology.
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message=t('progress.ontologySet')
            )
            
            # 3. Split source text into chunks.
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=t('progress.textSplit', count=total_chunks)
            )
            
            # 4. Push chunks to the graph in batches.
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )
            
            # 5. Wait for Graphiti to finish processing the episodes.
            self.task_manager.update_task(
                task_id,
                progress=60,
                message=t('progress.waitingGraphProcess')
            )
            
            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )
            
            # 6. Fetch the final graph metadata.
            self.task_manager.update_task(
                task_id,
                progress=90,
                message=t('progress.fetchingGraphInfo')
            )
            
            graph_info = self._get_graph_info(graph_id)

            # Symmetric "non-zero entities" gate matching _recover_stuck_projects:
            # if add_batch returned cleanly but Graphiti wrote no entities (e.g.,
            # the embedder swallowed input or produced wrong-dim vectors that the
            # Neo4j index rejected without raising), surface a loud failure instead
            # of marking the task COMPLETED on an empty graph.
            if graph_info.node_count == 0:
                logger.error(
                    "graph build produced 0 entities for group_id=%s (task=%s)",
                    graph_id, task_id,
                )
                self.task_manager.fail_task(task_id, t('progress.emptyGraphFailure'))
                return

            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """Create a new graph and return its id (public API)."""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        
        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )
        
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """Register the ontology with the graph (Graphiti uses it as an extraction prompt)."""
        self.client.graph.set_ontology(
            graph_ids=[graph_id],
            entities=ontology.get("entity_types"),
            edges=ontology.get("edge_types"),
        )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
        skip_chunks: int = 0,
    ) -> List[str]:
        """Push chunks to the graph in batches; returns the uuids of all episodes added.

        Args:
            skip_chunks: Number of chunks to skip (used for resume-after-restart).
        """
        episode_uuids = []
        total_chunks = len(chunks)

        for i in range(skip_chunks, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    t('progress.sendingBatch', current=batch_num, total=total_batches, chunks=len(batch_chunks)),
                    progress
                )

            
            # Build the per-episode payload structures expected by the client.
            episodes = [
                type('Episode', (), {'data': chunk, 'type': 'text'})()
                for chunk in batch_chunks
            ]
            
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )

                # Collect the uuids returned for each episode.
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)

                # Throttle to avoid overwhelming the upstream API.
                time.sleep(1)
                
            except Exception as e:
                if progress_callback:
                    progress_callback(t('progress.batchFailed', batch=batch_num, error=str(e)), 0)
                raise
        
        return episode_uuids
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """Poll each episode until Graphiti marks it processed, or the timeout expires."""
        if not episode_uuids:
            if progress_callback:
                progress_callback(t('progress.noEpisodesWait'), 1.0)
            return
        
        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)
        
        if progress_callback:
            progress_callback(t('progress.waitingEpisodes', count=total_episodes), 0)
        
        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        t('progress.episodesTimeout', completed=completed_count, total=total_episodes),
                        completed_count / total_episodes
                    )
                break
            
            # Check the processing state of each pending episode.
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)

                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1

                except Exception as e:
                    # Tolerate a single failed query; the next loop iteration retries.
                    pass
            
            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    t('progress.graphProcessing', completed=completed_count, total=total_episodes, pending=len(pending_episodes), elapsed=elapsed),
                    completed_count / total_episodes if total_episodes > 0 else 0
                )
            
            if pending_episodes:
                time.sleep(3)  # poll every 3 seconds
        
        if progress_callback:
            progress_callback(t('progress.processingComplete', completed=completed_count, total=total_episodes), 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Fetch summary info (counts and entity types) for a graph."""
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # Tally distinct entity types across all nodes.
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str, ontology: Optional[Dict] = None) -> Dict[str, Any]:
        """Return the full graph payload including timestamps, attributes, and edges.

        Args:
            graph_id: Graph identifier.

        Returns:
            Dict with ``nodes``, ``edges``, and aggregate counts.
        """
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # Build a uuid->name map so edge endpoints can be labeled.
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""

        nodes_data = []
        for node in nodes:
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            entity_type = _classify_entity_type(node.name, node.summary or "", ontology)
            labels = node.labels or []
            if entity_type != "Entity" and entity_type not in labels:
                labels = [entity_type] + [l for l in labels if l != "Entity"]

            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": labels,
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })
        
        edges_data = []
        for edge in edges:
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)

            # Normalize the episode list (the field may be missing or a single id).
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]

            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""
            
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """Delete a graph by id."""
        self.client.graph.delete(graph_id=graph_id)

