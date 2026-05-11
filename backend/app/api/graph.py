"""
Graph-related API routes.

Uses a project context mechanism with server-side state persistence.
"""

import os
import time
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..utils.locale import t

# In-memory cache for graph data. Originally added for Zep's rate-limited API;
# Neo4j is local so the cache mostly smooths concurrent polls during a build.
_graph_data_cache: dict = {}        # graph_id -> {"data": ..., "ts": float}
_graph_refresh_locks: dict = {}     # graph_id -> threading.Lock (one refresh at a time)
_GRAPH_CACHE_TTL = 300              # seconds before triggering a background refresh
# Empty results use a much shorter TTL: during a build, the first poll may land
# before Graphiti has finished extracting entities, and a 5-minute fresh-cache
# of {nodes: 0, edges: 0} would mask the real data once it appears.
_GRAPH_EMPTY_CACHE_TTL = 5

logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """Return True if the file extension is in the allowed list."""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Project management endpoints ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """Get project details."""
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t("api.error.graph.m001", project_id=project_id)
        }), 404
    
    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """List all projects."""
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """Delete a project."""
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": t("api.error.graph.m002", project_id=project_id)
        }), 404
    
    return jsonify({
        "success": True,
        "message": t("api.message.graph.m003", project_id=project_id)
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """Reset project state (used to rebuild the graph from scratch)."""
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t("api.error.graph.m004", project_id=project_id)
        }), 404
    
    # Roll back to the "ontology generated" state so the next build can resume
    # from the existing ontology rather than re-running ontology generation.
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": t("api.message.graph.m005", project_id=project_id),
        "data": project.to_dict()
    })


# ============== Endpoint 1: upload files and generate ontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """Endpoint 1: upload files, analyze them, and generate an ontology definition.

    Request format: multipart/form-data.

    Args:
        files: Uploaded files (PDF/MD/TXT); one or more.
        simulation_requirement: Description of the simulation requirement (required).
        project_name: Project name (optional).
        additional_context: Additional context (optional).

    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info(t("log.graph_api.m006"))

        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(t("log.graph_api.m007", project_name=project_name))
        logger.debug(t("log.graph_api.m008", simulation_requirement=simulation_requirement[:100]))
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m009")
            }), 400
        
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m010")
            }), 400
        
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(t("log.graph_api.m011", project=project.project_id))
        
        # Persist each uploaded file under the project's directory and pull its
        # text out so the ontology generator has plain text to work with.
        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m012")
            }), 400
        
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(t("log.graph_api.m013", len=len(all_text)))
        
        logger.info(t("log.graph_api.m014"))
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(t("log.graph_api.m015", entity_count=entity_count, edge_count=edge_count))
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(t("log.graph_api.m016", project=project.project_id))
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Endpoint 2: build graph ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """Endpoint 2: build the graph for the given project_id.

    Request (JSON):
        {
            "project_id": "proj_xxxx",  // required, from endpoint 1
            "graph_name": "Graph name",  // optional
            "chunk_size": 500,           // optional, default 500
            "chunk_overlap": 50          // optional, default 50
        }

    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Graph build task started"
            }
        }
    """
    try:
        logger.info(t("log.graph_api.m017"))

        errors = []
        if not Config.NEO4J_PASSWORD:
            errors.append("NEO4J未配置")
        if errors:
            logger.error(t("log.graph_api.m018", errors=errors))
            return jsonify({
                "success": False,
                "error": "配置错误: " + "; ".join(errors)
            }), 500
        
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(t("log.graph_api.m019", project_id=project_id))
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m020")
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m021", project_id=project_id)
            }), 404
        
        # If True, abandon any existing build progress and rebuild from scratch.
        force = data.get('force', False)
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m022")
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m023"),
                "task_id": project.graph_build_task_id
            }), 400
        
        # On a forced rebuild, drop any prior build artifacts so we restart cleanly.
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m024")
            }), 400
        
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m025")
            }), 400
        
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")
        logger.info(t("log.graph_api.m026", task_id=task_id, project_id=project_id))
        
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(t("log.graph_api.m027", task_id=task_id))
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="初始化图谱构建服务..."
                )
                
                builder = GraphBuilderService()

                task_manager.update_task(
                    task_id,
                    message="文本分块中...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)

                task_manager.update_task(
                    task_id,
                    message="创建Zep图谱...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)

                project.graph_id = graph_id
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    message="设置本体定义...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)

                # Add text. The progress_callback signature is (msg, progress_ratio).
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # maps ratio onto 15%-55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                # Count already-processed episodes to resume after a restart
                from app.services.graphiti_adapter import _get_graphiti, _run, _neo4j_query
                try:
                    g = _get_graphiti()
                    ep_count = _run(_neo4j_query(g,
                        'MATCH (e:Episodic {group_id: $gid}) RETURN count(e) AS n',
                        {'gid': graph_id}
                    ))
                    already_done = int(ep_count[0]['n']) if ep_count else 0
                except Exception:
                    already_done = 0

                skip_chunks = already_done
                remaining = total_chunks - skip_chunks
                msg_start = (f"断点续传：跳过 {skip_chunks} 个已处理块，继续处理 {remaining} 块..."
                             if skip_chunks > 0 else f"开始添加 {total_chunks} 个文本块...")
                task_manager.update_task(task_id, message=msg_start, progress=15)

                episode_uuids = builder.add_text_batches(
                    graph_id,
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback,
                    skip_chunks=skip_chunks,
                )
                
                # Wait for Zep to finish processing (poll each episode's processed flag).
                task_manager.update_task(
                    task_id,
                    message="等待Zep处理数据...",
                    progress=55
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # maps ratio onto 55%-90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)

                task_manager.update_task(
                    task_id,
                    message="获取图谱数据...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)

                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(t(
                    "log.graph_api.m028",
                    task_id=task_id,
                    graph_id=graph_id,
                    node_count=node_count,
                    edge_count=edge_count,
                ))

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="图谱构建完成",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                # Mark the project as FAILED so the UI can surface the error.
                build_logger.error(t("log.graph_api.m029", task_id=task_id, e=str(e)))
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"构建失败: {str(e)}",
                    error=traceback.format_exc()
                )
        
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "图谱构建任务已启动，请通过 /task/{task_id} 查询进度"
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Task query endpoints ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """Query the status of a task."""
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": t("api.error.graph.m027", task_id=task_id)
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """List all tasks."""
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Graph data endpoints ==============

def _refresh_graph_cache(graph_id: str):
    """Background thread: fetch graph data from Neo4j and update cache."""
    lock = _graph_refresh_locks.setdefault(graph_id, threading.Lock())
    if not lock.acquire(blocking=False):
        return  # another refresh already in progress
    try:
        # Look up ontology from the project that owns this graph_id
        ontology = None
        for project in ProjectManager.list_projects():
            if project.graph_id == graph_id and project.ontology:
                ontology = project.ontology
                break

        builder = GraphBuilderService()
        graph_data = builder.get_graph_data(graph_id, ontology=ontology)
        _graph_data_cache[graph_id] = {"data": graph_data, "ts": time.time()}
        logger.info(f"Graph cache refreshed for {graph_id}")
    except Exception as e:
        logger.warning(f"Background graph cache refresh failed for {graph_id}: {str(e)[:100]}")
    finally:
        lock.release()


@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """Return graph data (nodes and edges).

    - Fresh cache: serve from cache without hitting Zep.
    - Stale cache: return the old cache immediately and refresh in the background.
    - No cache: kick off a background fetch and return 202 so the frontend retries.
    """
    if not Config.NEO4J_PASSWORD:
        return jsonify({"success": False, "error": t("api.error.graph.m028")}), 500

    cached = _graph_data_cache.get(graph_id)
    age = time.time() - cached["ts"] if cached else None

    if cached:
        data = cached["data"]
        is_empty = (data.get("node_count", 0) == 0) and (data.get("edge_count", 0) == 0)
        effective_ttl = _GRAPH_EMPTY_CACHE_TTL if is_empty else _GRAPH_CACHE_TTL
    else:
        effective_ttl = _GRAPH_CACHE_TTL

    if cached and age < effective_ttl:
        # Fresh cache — return immediately
        return jsonify({"success": True, "data": cached["data"], "cached": True})

    if cached:
        # Stale cache — serve it immediately, refresh in background
        threading.Thread(target=_refresh_graph_cache, args=(graph_id,), daemon=True).start()
        return jsonify({"success": True, "data": cached["data"], "cached": True, "stale": True})

    # No cache at all — kick off background fetch, tell frontend to retry
    threading.Thread(target=_refresh_graph_cache, args=(graph_id,), daemon=True).start()
    return jsonify({
        "success": False,
        "error": "Graph data is loading, please retry in a moment.",
        "retry": True
    }), 202


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """Delete a Zep graph."""
    try:
        if not Config.NEO4J_PASSWORD:
            return jsonify({
                "success": False,
                "error": t("api.error.graph.m029")
            }), 500
        
        builder = GraphBuilderService()
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": t("api.message.graph.m030", graph_id=graph_id)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
