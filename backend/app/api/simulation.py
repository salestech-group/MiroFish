"""Simulation-related API routes.

Step 2: Zep entity reading/filtering, OASIS simulation preparation and execution
(end-to-end automated).
"""

import os
import traceback
from flask import request, jsonify, send_file

from . import simulation_bp
from ..config import Config
from ..services.zep_entity_reader import ZepEntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager, SimulationStatus
from ..services.simulation_runner import SimulationRunner, RunnerStatus
from ..utils.logger import get_logger
from ..models.project import ProjectManager
from ..utils.locale import t

logger = get_logger('mirofish.api.simulation')


# Prefix injection avoids agent tool-calls and forces a plain-text reply.
INTERVIEW_PROMPT_PREFIX = "结合你的人设、所有的过往记忆与行动，不调用任何工具直接用文本回复我："


def optimize_interview_prompt(prompt: str) -> str:
    """Optimize an interview prompt by prepending the no-tool-call prefix.

    Args:
        prompt: Original prompt text.

    Returns:
        Prompt with the prefix prepended (or unchanged if already prefixed).
    """
    if not prompt:
        return prompt
    if prompt.startswith(INTERVIEW_PROMPT_PREFIX):
        return prompt
    return f"{INTERVIEW_PROMPT_PREFIX}{prompt}"


# ============== Entity reading endpoints ==============

@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """Return all (filtered) entities in the graph.

    Only nodes matching the predefined entity types are returned (i.e. nodes
    whose labels include more than just `Entity`).

    Query params:
        entity_types: Comma-separated entity-type list (optional, for further filtering).
        enrich: Whether to include related edge info (default true).
    """
    try:
        if not Config.NEO4J_PASSWORD:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m001")
            }), 500
        
        entity_types_str = request.args.get('entity_types', '')
        entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        logger.info(t("log.simulation_api.m002", graph_id=graph_id, entity_types=entity_types, enrich=enrich))
        
        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": result.to_dict()
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m003", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Return details for a single entity."""
    try:
        if not Config.NEO4J_PASSWORD:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m004")
            }), 500
        
        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)
        
        if not entity:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m005", entity_uuid=entity_uuid)
            }), 404
        
        return jsonify({
            "success": True,
            "data": entity.to_dict()
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m006", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Return all entities of the given type."""
    try:
        if not Config.NEO4J_PASSWORD:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m007")
            }), 500
        
        enrich = request.args.get('enrich', 'true').lower() == 'true'
        
        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich
        )
        
        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [e.to_dict() for e in entities]
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m008", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Simulation management endpoints ==============

@simulation_bp.route('/create', methods=['POST'])
def create_simulation():
    """Create a new simulation.

    Note: parameters such as `max_rounds` are generated intelligently by the LLM
    and do not need to be set manually.

    Request (JSON):
        {
            "project_id": "proj_xxxx",       // required
            "graph_id": "mirofish_xxxx",     // optional; falls back to the project's graph_id
            "enable_twitter": true,           // optional, default true
            "enable_reddit": true             // optional, default true
        }

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "project_id": "proj_xxxx",
                "graph_id": "mirofish_xxxx",
                "status": "created",
                "enable_twitter": true,
                "enable_reddit": true,
                "created_at": "2025-12-01T10:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        project_id = data.get('project_id')
        if not project_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m009")
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m010", project_id=project_id)
            }), 404
        
        graph_id = data.get('graph_id') or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m011")
            }), 400
        
        manager = SimulationManager()
        state = manager.create_simulation(
            project_id=project_id,
            graph_id=graph_id,
            enable_twitter=data.get('enable_twitter', True),
            enable_reddit=data.get('enable_reddit', True),
        )
        
        return jsonify({
            "success": True,
            "data": state.to_dict()
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m012", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _check_simulation_prepared(simulation_id: str) -> tuple:
    """Check whether a simulation is already fully prepared.

    Conditions:
    1. `state.json` exists and `status` is "ready".
    2. Required files exist: `reddit_profiles.json`, `twitter_profiles.csv`,
       `simulation_config.json`.

    Note: runner scripts (run_*.py) live under `backend/scripts/` and are no longer
    copied into the simulation directory.

    Args:
        simulation_id: Simulation identifier.

    Returns:
        (is_prepared: bool, info: dict)
    """
    import os
    from ..config import Config

    simulation_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

    if not os.path.exists(simulation_dir):
        return False, {"reason": t("api.simDirNotFound")}

    # Required files (scripts are not included; they live in backend/scripts/).
    required_files = [
        "state.json",
        "simulation_config.json",
        "reddit_profiles.json",
        "twitter_profiles.csv"
    ]

    existing_files = []
    missing_files = []
    for f in required_files:
        file_path = os.path.join(simulation_dir, f)
        if os.path.exists(file_path):
            existing_files.append(f)
        else:
            missing_files.append(f)
    
    if missing_files:
        return False, {
            "reason": t("api.simMissingRequiredFiles"),
            "missing_files": missing_files,
            "existing_files": existing_files
        }
    
    state_file = os.path.join(simulation_dir, "state.json")
    try:
        import json
        with open(state_file, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
        
        status = state_data.get("status", "")
        config_generated = state_data.get("config_generated", False)

        logger.debug(t("log.simulation_api.m013", simulation_id=simulation_id, status=status, config_generated=config_generated))

        # All these statuses imply preparation is finished (when config_generated is True):
        # - ready / preparing / running / completed / stopped / failed.
        prepared_statuses = ["ready", "preparing", "running", "completed", "stopped", "failed"]
        if status in prepared_statuses and config_generated:
            profiles_file = os.path.join(simulation_dir, "reddit_profiles.json")
            config_file = os.path.join(simulation_dir, "simulation_config.json")

            profiles_count = 0
            if os.path.exists(profiles_file):
                with open(profiles_file, 'r', encoding='utf-8') as f:
                    profiles_data = json.load(f)
                    profiles_count = len(profiles_data) if isinstance(profiles_data, list) else 0

            # If status is "preparing" but the files are already complete, auto-promote to "ready".
            if status == "preparing":
                try:
                    state_data["status"] = "ready"
                    from datetime import datetime
                    state_data["updated_at"] = datetime.now().isoformat()
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state_data, f, ensure_ascii=False, indent=2)
                    logger.info(t("log.simulation_api.m014", simulation_id=simulation_id))
                    status = "ready"
                except Exception as e:
                    logger.warning(t("log.simulation_api.m015", e=e))
            
            logger.info(t("log.simulation_api.m016", simulation_id=simulation_id, status=status, config_generated=config_generated))
            return True, {
                "status": status,
                "entities_count": state_data.get("entities_count", 0),
                "profiles_count": profiles_count,
                "entity_types": state_data.get("entity_types", []),
                "config_generated": config_generated,
                "created_at": state_data.get("created_at"),
                "updated_at": state_data.get("updated_at"),
                "existing_files": existing_files
            }
        else:
            logger.warning(t("log.simulation_api.m017", simulation_id=simulation_id, status=status, config_generated=config_generated))
            return False, {
                "reason": t("api.simStatusNotPrepared", status=status, config_generated=config_generated),
                "status": status,
                "config_generated": config_generated
            }

    except Exception as e:
        return False, {"reason": t("api.simStatusFileReadFailed", error=str(e))}


@simulation_bp.route('/prepare', methods=['POST'])
def prepare_simulation():
    """Prepare the simulation environment (async task; the LLM generates all params).

    This is a long-running operation. The endpoint returns a `task_id` immediately;
    use `GET /api/simulation/prepare/status` to poll for progress.

    Features:
    - Auto-detects completed preparation work and avoids duplicate generation.
    - Returns existing results when preparation is already complete.
    - Supports force regeneration via `force_regenerate=true`.

    Steps:
    1. Check whether preparation is already complete.
    2. Read and filter entities from the Zep graph.
    3. Generate an OASIS Agent profile per entity (with retry).
    4. LLM-generate the simulation configuration (with retry).
    5. Save the config files and preset scripts.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",                   // required
            "entity_types": ["Student", "PublicFigure"],   // optional
            "use_llm_for_profiles": true,                  // optional
            "parallel_profile_count": 5,                   // optional, default 5
            "force_regenerate": false                      // optional, default false
        }

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",            // present for newly started tasks
                "status": "preparing|ready",
                "message": "...",
                "already_prepared": true|false
            }
        }
    """
    import threading
    import os
    from ..models.task import TaskManager, TaskStatus
    from ..config import Config
    
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m018")
            }), 400
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m019", simulation_id=simulation_id)
            }), 404
        
        force_regenerate = data.get('force_regenerate', False)
        logger.info(t("log.simulation_api.m020", simulation_id=simulation_id, force_regenerate=force_regenerate))

        # Skip regeneration if preparation is already complete.
        if not force_regenerate:
            logger.debug(t("log.simulation_api.m021", simulation_id=simulation_id))
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            logger.debug(t("log.simulation_api.m022", is_prepared=is_prepared, prepare_info=prepare_info))
            if is_prepared:
                logger.info(t("log.simulation_api.m023", simulation_id=simulation_id))
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "message": t("api.alreadyPrepared"),
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
            else:
                logger.info(t("log.simulation_api.m024", simulation_id=simulation_id))
        
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m025", state=state.project_id)
            }), 404

        simulation_requirement = project.simulation_requirement or ""
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m026")
            }), 400

        document_text = ProjectManager.get_extracted_text(state.project_id) or ""

        entity_types_list = data.get('entity_types')
        use_llm_for_profiles = data.get('use_llm_for_profiles', True)
        parallel_profile_count = data.get('parallel_profile_count', 5)

        # Synchronously fetch the entity count before starting the background task,
        # so the frontend can immediately display the expected agent total.
        try:
            logger.info(t("log.simulation_api.m027", state=state.graph_id))
            reader = ZepEntityReader()
            filtered_preview = reader.filter_defined_entities(
                graph_id=state.graph_id,
                defined_entity_types=entity_types_list,
                enrich_with_edges=False  # Skip edges for speed; only the count matters here.
            )
            state.entities_count = filtered_preview.filtered_count
            state.entity_types = list(filtered_preview.entity_types)
            logger.info(t("log.simulation_api.m028", filtered_preview=filtered_preview.filtered_count, filtered_preview_2=filtered_preview.entity_types))
        except Exception as e:
            logger.warning(t("log.simulation_api.m029", e=e))
            # Failure here is non-fatal; the background task will re-read the entities.

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="simulation_prepare",
            metadata={
                "simulation_id": simulation_id,
                "project_id": state.project_id
            }
        )
        
        # Update simulation state (including the pre-fetched entity count).
        state.status = SimulationStatus.PREPARING
        manager._save_simulation_state(state)

        def run_prepare():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message=t("task.simulation.prepare.startMessage")
                )
                
                # Per-stage progress detail (used by the progress callback below).
                stage_details = {}

                def progress_callback(stage, progress, message, **kwargs):
                    # Map each stage to a slice of the overall 0-100 progress range.
                    stage_weights = {
                        "reading": (0, 20),
                        "generating_profiles": (20, 70),
                        "generating_config": (70, 90),
                        "copying_scripts": (90, 100)
                    }

                    start, end = stage_weights.get(stage, (0, 100))
                    current_progress = int(start + (end - start) * progress / 100)

                    stage_names = {
                        "reading": t("task.simulation.prepare.stage.reading"),
                        "generating_profiles": t("task.simulation.prepare.stage.generatingProfiles"),
                        "generating_config": t("task.simulation.prepare.stage.generatingConfig"),
                        "copying_scripts": t("task.simulation.prepare.stage.copyingScripts")
                    }
                    
                    stage_index = list(stage_weights.keys()).index(stage) + 1 if stage in stage_weights else 1
                    total_stages = len(stage_weights)

                    stage_details[stage] = {
                        "stage_name": stage_names.get(stage, stage),
                        "stage_progress": progress,
                        "current": kwargs.get("current", 0),
                        "total": kwargs.get("total", 0),
                        "item_name": kwargs.get("item_name", "")
                    }

                    detail = stage_details[stage]
                    progress_detail_data = {
                        "current_stage": stage,
                        "current_stage_name": stage_names.get(stage, stage),
                        "stage_index": stage_index,
                        "total_stages": total_stages,
                        "stage_progress": progress,
                        "current_item": detail["current"],
                        "total_items": detail["total"],
                        "item_description": message
                    }

                    # Build a concise progress message.
                    if detail["total"] > 0:
                        detailed_message = (
                            f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: "
                            f"{detail['current']}/{detail['total']} - {message}"
                        )
                    else:
                        detailed_message = f"[{stage_index}/{total_stages}] {stage_names.get(stage, stage)}: {message}"
                    
                    task_manager.update_task(
                        task_id,
                        progress=current_progress,
                        message=detailed_message,
                        progress_detail=progress_detail_data
                    )
                
                result_state = manager.prepare_simulation(
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement,
                    document_text=document_text,
                    defined_entity_types=entity_types_list,
                    use_llm_for_profiles=use_llm_for_profiles,
                    progress_callback=progress_callback,
                    parallel_profile_count=parallel_profile_count
                )
                
                task_manager.complete_task(
                    task_id,
                    result=result_state.to_simple_dict()
                )

            except Exception as e:
                logger.error(t("log.simulation_api.m030", str=str(e)))
                task_manager.fail_task(task_id, str(e))

                # Mark the simulation state as failed.
                state = manager.get_simulation(simulation_id)
                if state:
                    state.status = SimulationStatus.FAILED
                    state.error = str(e)
                    manager._save_simulation_state(state)

        thread = threading.Thread(target=run_prepare, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "task_id": task_id,
                "status": "preparing",
                "message": t("api.prepareStarted"),
                "already_prepared": False,
                "expected_entities_count": state.entities_count,  # Expected total agent count.
                "entity_types": state.entity_types  # Entity-type list.
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(t("log.simulation_api.m031", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/prepare/status', methods=['POST'])
def get_prepare_status():
    """Query progress for a preparation task.

    Two query modes are supported:
    1. By `task_id` — return live progress for an in-flight task.
    2. By `simulation_id` — check whether preparation has already finished.

    Request (JSON):
        {
            "task_id": "task_xxxx",          // optional; the task_id returned by /prepare
            "simulation_id": "sim_xxxx"      // optional; checks for existing complete prep
        }

    Response:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|ready",
                "progress": 45,
                "message": "...",
                "already_prepared": true|false,  // whether prep is already complete
                "prepare_info": {...}            // details when prep is complete
            }
        }
    """
    from ..models.task import TaskManager
    
    try:
        data = request.get_json() or {}
        
        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')
        
        # If simulation_id is provided, first check if prep is already complete.
        if simulation_id:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
            if is_prepared:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "ready",
                        "progress": 100,
                        "message": t("api.alreadyPreparedShort"),
                        "already_prepared": True,
                        "prepare_info": prepare_info
                    }
                })
        
        # No task_id provided.
        if not task_id:
            if simulation_id:
                # simulation_id provided but prep is not complete.
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "status": "not_started",
                        "progress": 0,
                        "message": t("api.notStartedPrepare"),
                        "already_prepared": False
                    }
                })
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m032")
            }), 400
        
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        
        if not task:
            # Task is missing; if simulation_id is given, check whether prep is already complete.
            if simulation_id:
                is_prepared, prepare_info = _check_simulation_prepared(simulation_id)
                if is_prepared:
                    return jsonify({
                        "success": True,
                        "data": {
                            "simulation_id": simulation_id,
                            "task_id": task_id,
                            "status": "ready",
                            "progress": 100,
                            "message": t("api.taskCompletedPrepared"),
                            "already_prepared": True,
                            "prepare_info": prepare_info
                        }
                    })
            
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m033", task_id=task_id)
            }), 404
        
        task_dict = task.to_dict()
        task_dict["already_prepared"] = False
        
        return jsonify({
            "success": True,
            "data": task_dict
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m034", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@simulation_bp.route('/<simulation_id>', methods=['GET'])
def get_simulation(simulation_id: str):
    """Return the current simulation state."""
    try:
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        
        if not state:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m035", simulation_id=simulation_id)
            }), 404
        
        result = state.to_dict()
        
        # Attach run instructions when the simulation is ready.
        if state.status == SimulationStatus.READY:
            result["run_instructions"] = manager.get_run_instructions(simulation_id)
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m036", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/list', methods=['GET'])
def list_simulations():
    """List all simulations.

    Query params:
        project_id: Filter by project ID (optional).
    """
    try:
        project_id = request.args.get('project_id')
        
        manager = SimulationManager()
        simulations = manager.list_simulations(project_id=project_id)
        
        return jsonify({
            "success": True,
            "data": [s.to_dict() for s in simulations],
            "count": len(simulations)
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m037", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """Return the latest report_id associated with a simulation.

    Walks the reports directory, finds reports whose simulation_id matches,
    and returns the most recent one (sorted by created_at).

    Args:
        simulation_id: Simulation identifier.

    Returns:
        report_id, or None if no matching report exists.
    """
    import json
    from datetime import datetime

    # Reports directory: backend/uploads/reports.
    # __file__ is app/api/simulation.py, so we go up two levels to reach backend/.
    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None
    
    matching_reports = []
    
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue
            
            meta_file = os.path.join(report_path, "meta.json")
            if not os.path.exists(meta_file):
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                if meta.get("simulation_id") == simulation_id:
                    matching_reports.append({
                        "report_id": meta.get("report_id"),
                        "created_at": meta.get("created_at", ""),
                        "status": meta.get("status", "")
                    })
            except Exception:
                continue
        
        if not matching_reports:
            return None
        
        # Sort by creation time descending and return the most recent.
        matching_reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matching_reports[0].get("report_id")
        
    except Exception as e:
        logger.warning(t("log.simulation_api.m038", simulation_id=simulation_id, e=e))
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """Return historical simulations (with project details).

    Used by the homepage to display past projects. Returns a list of simulations
    enriched with project name, description, and other metadata.

    Query params:
        limit: Maximum number of items to return (default 20).

    Response:
        {
            "success": true,
            "data": [
                {
                    "simulation_id": "sim_xxxx",
                    "project_id": "proj_xxxx",
                    "project_name": "...",
                    "simulation_requirement": "...",
                    "status": "completed",
                    "entities_count": 68,
                    "profiles_count": 68,
                    "entity_types": ["Student", "Professor", ...],
                    "created_at": "2024-12-10",
                    "updated_at": "2024-12-10",
                    "total_rounds": 120,
                    "current_round": 120,
                    "report_id": "report_xxxx",
                    "version": "v1.0.2"
                },
                ...
            ],
            "count": 7
        }
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]
        
        # Enrich simulation data using only the Simulation files.
        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()

            # Read simulation_requirement from simulation_config.json.
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict["simulation_requirement"] = config.get("simulation_requirement", "")
                time_config = config.get("time_config", {})
                sim_dict["total_simulation_hours"] = time_config.get("total_simulation_hours", 0)
                # Recommended round count (used as a fallback).
                recommended_rounds = int(
                    time_config.get("total_simulation_hours", 0) * 60 /
                    max(time_config.get("minutes_per_round", 60), 1)
                )
            else:
                sim_dict["simulation_requirement"] = ""
                sim_dict["total_simulation_hours"] = 0
                recommended_rounds = 0

            # Read user-set total_rounds from run_state.json.
            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict["current_round"] = run_state.current_round
                sim_dict["runner_status"] = run_state.runner_status.value
                # Prefer the user-set total_rounds; fall back to the recommended count.
                sim_dict["total_rounds"] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict["current_round"] = 0
                sim_dict["runner_status"] = "idle"
                sim_dict["total_rounds"] = recommended_rounds

            # Up to three files from the associated project.
            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict["files"] = [
                    {"filename": f.get("filename", t("api.unknownFilename"))}
                    for f in project.files[:3]
                ]
            else:
                sim_dict["files"] = []

            # Latest report_id linked to this simulation.
            sim_dict["report_id"] = _get_report_id_for_simulation(sim.simulation_id)

            sim_dict["version"] = "v1.0.2"

            try:
                created_date = sim_dict.get("created_at", "")[:10]
                sim_dict["created_date"] = created_date
            except:
                sim_dict["created_date"] = ""
            
            enriched_simulations.append(sim_dict)
        
        return jsonify({
            "success": True,
            "data": enriched_simulations,
            "count": len(enriched_simulations)
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m039", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles', methods=['GET'])
def get_simulation_profiles(simulation_id: str):
    """Return the agent profiles for a simulation.

    Query params:
        platform: Platform (reddit/twitter, default reddit).
    """
    try:
        platform = request.args.get('platform', 'reddit')
        
        manager = SimulationManager()
        profiles = manager.get_profiles(simulation_id, platform=platform)
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "count": len(profiles),
                "profiles": profiles
            }
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404
        
    except Exception as e:
        logger.error(t("log.simulation_api.m040", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/profiles/realtime', methods=['GET'])
def get_simulation_profiles_realtime(simulation_id: str):
    """Return agent profiles in real time (for live progress during generation).

    Differs from /profiles in that:
    - Reads files directly, bypassing SimulationManager.
    - Suitable for live viewing while generation is still running.
    - Returns extra metadata (file mtime, is_generating, etc.).

    Query params:
        platform: Platform (reddit/twitter, default reddit).

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "platform": "reddit",
                "count": 15,
                "total_expected": 93,   // expected total (if known)
                "is_generating": true,  // whether generation is in progress
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "profiles": [...]
            }
        }
    """
    import json
    import csv
    from datetime import datetime
    
    try:
        platform = request.args.get('platform', 'reddit')
        
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m041", simulation_id=simulation_id)
            }), 404

        if platform == "reddit":
            profiles_file = os.path.join(sim_dir, "reddit_profiles.json")
        else:
            profiles_file = os.path.join(sim_dir, "twitter_profiles.csv")

        file_exists = os.path.exists(profiles_file)
        profiles = []
        file_modified_at = None
        
        if file_exists:
            file_stat = os.stat(profiles_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()

            try:
                if platform == "reddit":
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        profiles = json.load(f)
                else:
                    with open(profiles_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        profiles = list(reader)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(t("log.simulation_api.m042", e=e))
                profiles = []

        # Use state.json to detect whether generation is in progress.
        is_generating = False
        total_expected = None
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    total_expected = state_data.get("entities_count")
            except Exception:
                pass
        
        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "platform": platform,
                "count": len(profiles),
                "total_expected": total_expected,
                "is_generating": is_generating,
                "file_exists": file_exists,
                "file_modified_at": file_modified_at,
                "profiles": profiles
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m043", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/realtime', methods=['GET'])
def get_simulation_config_realtime(simulation_id: str):
    """Return the simulation config in real time (for live progress during generation).

    Differs from /config in that:
    - Reads the file directly, bypassing SimulationManager.
    - Suitable for live viewing while generation is still running.
    - Returns extra metadata (file mtime, is_generating, etc.).
    - Returns partial information even if generation has not finished.

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "file_exists": true,
                "file_modified_at": "2025-12-04T18:20:00",
                "is_generating": true,                  // generation in progress
                "generation_stage": "generating_config", // current stage
                "config": {...}                          // config content, if any
            }
        }
    """
    import json
    from datetime import datetime
    
    try:
        sim_dir = os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id)

        if not os.path.exists(sim_dir):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m044", simulation_id=simulation_id)
            }), 404

        config_file = os.path.join(sim_dir, "simulation_config.json")

        file_exists = os.path.exists(config_file)
        config = None
        file_modified_at = None

        if file_exists:
            file_stat = os.stat(config_file)
            file_modified_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(t("log.simulation_api.m045", e=e))
                config = None

        # Use state.json to detect whether generation is in progress.
        is_generating = False
        generation_stage = None
        config_generated = False
        
        state_file = os.path.join(sim_dir, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    status = state_data.get("status", "")
                    is_generating = status == "preparing"
                    config_generated = state_data.get("config_generated", False)

                    # Derive the current stage.
                    if is_generating:
                        if state_data.get("profiles_generated", False):
                            generation_stage = "generating_config"
                        else:
                            generation_stage = "generating_profiles"
                    elif status == "ready":
                        generation_stage = "completed"
            except Exception:
                pass

        response_data = {
            "simulation_id": simulation_id,
            "file_exists": file_exists,
            "file_modified_at": file_modified_at,
            "is_generating": is_generating,
            "generation_stage": generation_stage,
            "config_generated": config_generated,
            "config": config
        }

        # When config is present, surface a few key summary stats.
        if config:
            response_data["summary"] = {
                "total_agents": len(config.get("agent_configs", [])),
                "simulation_hours": config.get("time_config", {}).get("total_simulation_hours"),
                "initial_posts_count": len(config.get("event_config", {}).get("initial_posts", [])),
                "hot_topics_count": len(config.get("event_config", {}).get("hot_topics", [])),
                "has_twitter_config": "twitter_config" in config,
                "has_reddit_config": "reddit_config" in config,
                "generated_at": config.get("generated_at"),
                "llm_model": config.get("llm_model")
            }
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m046", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config', methods=['GET'])
def get_simulation_config(simulation_id: str):
    """Return the simulation config (the full LLM-generated config).

    Returns:
        - time_config: Time configuration (sim length, rounds, peak/off-peak windows).
        - agent_configs: Per-agent activity configuration (activity, posting rate, stance).
        - event_config: Event configuration (initial posts, hot topics).
        - platform_configs: Platform configuration.
        - generation_reasoning: The LLM's reasoning notes for the config.
    """
    try:
        manager = SimulationManager()
        config = manager.get_simulation_config(simulation_id)
        
        if not config:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m047")
            }), 404
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m048", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/config/download', methods=['GET'])
def download_simulation_config(simulation_id: str):
    """Download the simulation config file."""
    try:
        manager = SimulationManager()
        sim_dir = manager._get_simulation_dir(simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m049")
            }), 404
        
        return send_file(
            config_path,
            as_attachment=True,
            download_name="simulation_config.json"
        )
        
    except Exception as e:
        logger.error(t("log.simulation_api.m050", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/script/<script_name>/download', methods=['GET'])
def download_simulation_script(script_name: str):
    """Download a simulation runner script (shared scripts in backend/scripts/).

    Allowed values for script_name:
        - run_twitter_simulation.py
        - run_reddit_simulation.py
        - run_parallel_simulation.py
        - action_logger.py
    """
    try:
        # Scripts live in the backend/scripts/ directory.
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../scripts'))

        # Allow only known script names.
        allowed_scripts = [
            "run_twitter_simulation.py",
            "run_reddit_simulation.py", 
            "run_parallel_simulation.py",
            "action_logger.py"
        ]
        
        if script_name not in allowed_scripts:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m051", script_name=script_name, allowed_scripts=allowed_scripts)
            }), 400
        
        script_path = os.path.join(scripts_dir, script_name)
        
        if not os.path.exists(script_path):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m052", script_name=script_name)
            }), 404
        
        return send_file(
            script_path,
            as_attachment=True,
            download_name=script_name
        )
        
    except Exception as e:
        logger.error(t("log.simulation_api.m053", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Standalone profile generation endpoints ==============

@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """Generate OASIS agent profiles directly from a graph (without creating a simulation).

    Request (JSON):
        {
            "graph_id": "mirofish_xxxx",     // required
            "entity_types": ["Student"],     // optional
            "use_llm": true,                 // optional
            "platform": "reddit"             // optional
        }
    """
    try:
        data = request.get_json() or {}
        
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m054")
            }), 400
        
        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')
        
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True
        )
        
        if filtered.filtered_count == 0:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m055")
            }), 400
        
        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(
            entities=filtered.entities,
            use_llm=use_llm
        )
        
        if platform == "reddit":
            profiles_data = [p.to_reddit_format() for p in profiles]
        elif platform == "twitter":
            profiles_data = [p.to_twitter_format() for p in profiles]
        else:
            profiles_data = [p.to_dict() for p in profiles]
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m056", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Simulation run-control endpoints ==============

@simulation_bp.route('/start', methods=['POST'])
def start_simulation():
    """Start running a simulation.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",           // required
            "platform": "parallel",                 // optional: twitter / reddit / parallel (default)
            "max_rounds": 100,                      // optional: max simulation rounds (truncate long sims)
            "enable_graph_memory_update": false,    // optional: stream agent activity into Zep memory
            "force": false                          // optional: force restart (stops running sim, clears logs)
        }

    About `force`:
        - When enabled, if the simulation is running or completed, it is stopped and run logs are cleared.
        - Cleared artefacts: run_state.json, actions.jsonl, simulation.log, etc.
        - Config files (simulation_config.json) and profiles are NOT cleared.
        - Use this when you need to re-run a simulation from scratch.

    About `enable_graph_memory_update`:
        - When enabled, all agent activity (posts, comments, likes, etc.) is pushed into the Zep graph
          in real time, so the graph "remembers" the simulation for later analysis or chat.
        - Requires the linked project to have a valid graph_id.
        - Uses batch updates to reduce API calls.

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "process_pid": 12345,
                "twitter_running": true,
                "reddit_running": true,
                "started_at": "2025-12-01T10:00:00",
                "graph_memory_update_enabled": true,  // graph memory update was enabled
                "force_restarted": true               // restart was forced
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m057")
            }), 400

        platform = data.get('platform', 'parallel')
        max_rounds = data.get('max_rounds')  # optional: max simulation rounds
        enable_graph_memory_update = data.get('enable_graph_memory_update', False)  # optional: enable graph memory update
        force = data.get('force', False)  # optional: force restart

        if max_rounds is not None:
            try:
                max_rounds = int(max_rounds)
                if max_rounds <= 0:
                    return jsonify({
                        "success": False,
                        "error": t("api.error.simulation.m058")
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m059")
                }), 400

        if platform not in ['twitter', 'reddit', 'parallel']:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m060", platform=platform)
            }), 400

        # Verify the simulation is ready.
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m061", simulation_id=simulation_id)
            }), 404

        force_restarted = False

        # If preparation is complete, allow re-starting even from a non-READY status.
        if state.status != SimulationStatus.READY:
            is_prepared, prepare_info = _check_simulation_prepared(simulation_id)

            if is_prepared:
                # Preparation is complete; check whether a process is still running.
                if state.status == SimulationStatus.RUNNING:
                    run_state = SimulationRunner.get_run_state(simulation_id)
                    if run_state and run_state.runner_status.value == "running":
                        # The process is genuinely running.
                        if force:
                            # Force mode: stop the running simulation.
                            logger.info(t("log.simulation_api.m062", simulation_id=simulation_id))
                            try:
                                SimulationRunner.stop_simulation(simulation_id)
                            except Exception as e:
                                logger.warning(t("log.simulation_api.m063", str=str(e)))
                        else:
                            return jsonify({
                                "success": False,
                                "error": t("api.error.simulation.m064")
                            }), 400

                # When forcing, also clear run logs.
                if force:
                    logger.info(t("log.simulation_api.m065", simulation_id=simulation_id))
                    cleanup_result = SimulationRunner.cleanup_simulation_logs(simulation_id)
                    if not cleanup_result.get("success"):
                        logger.warning(t("log.simulation_api.m066", cleanup_result=cleanup_result.get('errors')))
                    force_restarted = True

                # Process is gone or finished; reset status to ready.
                logger.info(t("log.simulation_api.m067", simulation_id=simulation_id, state=state.status.value))
                state.status = SimulationStatus.READY
                manager._save_simulation_state(state)
            else:
                # Preparation has not finished.
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m068", state=state.status.value)
                }), 400

        # Resolve graph_id (used by graph memory update).
        graph_id = None
        if enable_graph_memory_update:
            graph_id = state.graph_id
            if not graph_id:
                # Fall back to the project's graph_id.
                project = ProjectManager.get_project(state.project_id)
                if project:
                    graph_id = project.graph_id

            if not graph_id:
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m069")
                }), 400

            logger.info(t("log.simulation_api.m070", simulation_id=simulation_id, graph_id=graph_id))

        run_state = SimulationRunner.start_simulation(
            simulation_id=simulation_id,
            platform=platform,
            max_rounds=max_rounds,
            enable_graph_memory_update=enable_graph_memory_update,
            graph_id=graph_id
        )

        state.status = SimulationStatus.RUNNING
        manager._save_simulation_state(state)
        
        response_data = run_state.to_dict()
        if max_rounds:
            response_data['max_rounds_applied'] = max_rounds
        response_data['graph_memory_update_enabled'] = enable_graph_memory_update
        response_data['force_restarted'] = force_restarted
        if enable_graph_memory_update:
            response_data['graph_id'] = graph_id
        
        return jsonify({
            "success": True,
            "data": response_data
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(t("log.simulation_api.m071", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/stop', methods=['POST'])
def stop_simulation():
    """Stop a simulation.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // required
        }

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "stopped",
                "completed_at": "2025-12-01T12:00:00"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m072")
            }), 400
        
        run_state = SimulationRunner.stop_simulation(simulation_id)

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.PAUSED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(t("log.simulation_api.m073", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Real-time status monitoring endpoints ==============

@simulation_bp.route('/<simulation_id>/run-status', methods=['GET'])
def get_run_status(simulation_id: str):
    """Return real-time simulation run status (for frontend polling).

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                "total_rounds": 144,
                "progress_percent": 3.5,
                "simulated_hours": 2,
                "total_simulation_hours": 72,
                "twitter_running": true,
                "reddit_running": true,
                "twitter_actions_count": 150,
                "reddit_actions_count": 200,
                "total_actions_count": 350,
                "started_at": "2025-12-01T10:00:00",
                "updated_at": "2025-12-01T10:30:00"
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "current_round": 0,
                    "total_rounds": 0,
                    "progress_percent": 0,
                    "twitter_actions_count": 0,
                    "reddit_actions_count": 0,
                    "total_actions_count": 0,
                }
            })
        
        return jsonify({
            "success": True,
            "data": run_state.to_dict()
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m074", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/run-status/detail', methods=['GET'])
def get_run_status_detail(simulation_id: str):
    """Return detailed simulation run status (including all actions).

    Used by the frontend for live activity views.

    Query params:
        platform: Filter platform (twitter/reddit, optional).

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "runner_status": "running",
                "current_round": 5,
                ...
                "all_actions": [
                    {
                        "round_num": 5,
                        "timestamp": "2025-12-01T10:30:00",
                        "platform": "twitter",
                        "agent_id": 3,
                        "agent_name": "Agent Name",
                        "action_type": "CREATE_POST",
                        "action_args": {"content": "..."},
                        "result": null,
                        "success": true
                    },
                    ...
                ],
                "twitter_actions": [...],  # All actions on the Twitter platform
                "reddit_actions": [...]    # All actions on the Reddit platform
            }
        }
    """
    try:
        run_state = SimulationRunner.get_run_state(simulation_id)
        platform_filter = request.args.get('platform')
        
        if not run_state:
            return jsonify({
                "success": True,
                "data": {
                    "simulation_id": simulation_id,
                    "runner_status": "idle",
                    "all_actions": [],
                    "twitter_actions": [],
                    "reddit_actions": []
                }
            })
        
        all_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter
        )

        # Per-platform action lists.
        twitter_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="twitter"
        ) if not platform_filter or platform_filter == "twitter" else []

        reddit_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform="reddit"
        ) if not platform_filter or platform_filter == "reddit" else []

        # `recent_actions` only surfaces the latest round.
        current_round = run_state.current_round
        recent_actions = SimulationRunner.get_all_actions(
            simulation_id=simulation_id,
            platform=platform_filter,
            round_num=current_round
        ) if current_round > 0 else []

        result = run_state.to_dict()
        result["all_actions"] = [a.to_dict() for a in all_actions]
        result["twitter_actions"] = [a.to_dict() for a in twitter_actions]
        result["reddit_actions"] = [a.to_dict() for a in reddit_actions]
        result["rounds_count"] = len(run_state.rounds)
        result["recent_actions"] = [a.to_dict() for a in recent_actions]
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m075", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/actions', methods=['GET'])
def get_simulation_actions(simulation_id: str):
    """Return the agent action history for a simulation.

    Query params:
        limit: Number of items to return (default 100).
        offset: Offset (default 0).
        platform: Filter platform (twitter/reddit).
        agent_id: Filter agent ID.
        round_num: Filter round.

    Response:
        {
            "success": true,
            "data": {
                "count": 100,
                "actions": [...]
            }
        }
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        platform = request.args.get('platform')
        agent_id = request.args.get('agent_id', type=int)
        round_num = request.args.get('round_num', type=int)
        
        actions = SimulationRunner.get_actions(
            simulation_id=simulation_id,
            limit=limit,
            offset=offset,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(actions),
                "actions": [a.to_dict() for a in actions]
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m076", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/timeline', methods=['GET'])
def get_simulation_timeline(simulation_id: str):
    """Return the simulation timeline (summary per round).

    Used by the frontend for the progress bar and timeline view.

    Query params:
        start_round: Starting round (default 0).
        end_round: Ending round (default: all).

    Returns:
        Per-round summary info.
    """
    try:
        start_round = request.args.get('start_round', 0, type=int)
        end_round = request.args.get('end_round', type=int)
        
        timeline = SimulationRunner.get_timeline(
            simulation_id=simulation_id,
            start_round=start_round,
            end_round=end_round
        )
        
        return jsonify({
            "success": True,
            "data": {
                "rounds_count": len(timeline),
                "timeline": timeline
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m077", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/agent-stats', methods=['GET'])
def get_agent_stats(simulation_id: str):
    """Return per-agent statistics.

    Used by the frontend to show agent activity rankings, action distribution, etc.
    """
    try:
        stats = SimulationRunner.get_agent_stats(simulation_id)
        
        return jsonify({
            "success": True,
            "data": {
                "agents_count": len(stats),
                "stats": stats
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m078", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Database query endpoints ==============

@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """Return the posts created in a simulation.

    Query params:
        platform: Platform (twitter/reddit).
        limit: Number of items to return (default 50).
        offset: Offset.

    Returns:
        List of posts (read from the SQLite database).
    """
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_file = f"{platform}_simulation.db"
        db_path = os.path.join(sim_dir, db_file)
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": t("api.dbNotExist")
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM post 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            """, (limit, offset))
            
            posts = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
            
        except sqlite3.OperationalError:
            posts = []
            total = 0
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "total": total,
                "count": len(posts),
                "posts": posts
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m079", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """Return comments from a simulation (Reddit only).

    Query params:
        post_id: Filter by post ID (optional).
        limit: Number of items to return.
        offset: Offset.
    """
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        
        db_path = os.path.join(sim_dir, "reddit_simulation.db")
        
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "count": 0,
                    "comments": []
                }
            })
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment 
                    WHERE post_id = ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            
            comments = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.OperationalError:
            comments = []
        
        conn.close()
        
        return jsonify({
            "success": True,
            "data": {
                "count": len(comments),
                "comments": comments
            }
        })
        
    except Exception as e:
        logger.error(t("log.simulation_api.m080", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interview endpoints ==============

@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """Interview a single agent.

    Note: requires the simulation environment to be running (i.e. the sim loop has
    finished and the runner is in command-wait mode).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // required
            "agent_id": 0,                     // required
            "prompt": "...",                   // required, interview question
            "platform": "twitter",             // optional (twitter/reddit)
                                               //   omit -> dual-platform sims interview both platforms
            "timeout": 60                      // optional, timeout in seconds, default 60
        }

    Response (when `platform` is omitted; dual-platform mode):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "...",
                "result": {
                    "agent_id": 0,
                    "prompt": "...",
                    "platforms": {
                        "twitter": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit": {"agent_id": 0, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }

    Response (when `platform` is specified):
        {
            "success": true,
            "data": {
                "agent_id": 0,
                "prompt": "...",
                "result": {
                    "agent_id": 0,
                    "response": "...",
                    "platform": "twitter",
                    "timestamp": "2025-12-08T10:00:00"
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # optional: twitter / reddit / None
        timeout = data.get('timeout', 60)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m081")
            }), 400
        
        if agent_id is None:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m082")
            }), 400
        
        if not prompt:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m083")
            }), 400
        
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m084")
            }), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m085")
            }), 400

        # Inject the no-tool-call prefix into the prompt.
        optimized_prompt = optimize_interview_prompt(prompt)
        
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": t("api.error.simulation.m086", str=str(e))
        }), 504
        
    except Exception as e:
        logger.error(t("log.simulation_api.m087", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """Interview multiple agents in batch.

    Note: requires the simulation environment to be running.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",       // required
            "interviews": [                    // required
                {
                    "agent_id": 0,
                    "prompt": "...",
                    "platform": "twitter"      // optional, per-agent platform override
                },
                {
                    "agent_id": 1,
                    "prompt": "..."            // omit `platform` to use the default
                }
            ],
            "platform": "reddit",              // optional default platform (overridden by each item's platform)
                                               //   omit -> dual-platform sims interview each agent on both platforms
            "timeout": 120                     // optional, timeout in seconds, default 120
        }

    Response:
        {
            "success": true,
            "data": {
                "interviews_count": 2,
                "result": {
                    "interviews_count": 4,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        "twitter_1": {"agent_id": 1, "response": "...", "platform": "twitter"},
                        "reddit_1": {"agent_id": 1, "response": "...", "platform": "reddit"}
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        interviews = data.get('interviews')
        platform = data.get('platform')  # optional: twitter / reddit / None
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m088")
            }), 400

        if not interviews or not isinstance(interviews, list):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m089")
            }), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m090")
            }), 400

        # Validate each interview item.
        for i, interview in enumerate(interviews):
            if 'agent_id' not in interview:
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m091", i=i + 1)
                }), 400
            if 'prompt' not in interview:
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m092", i=i + 1)
                }), 400
            # Validate each item's platform (if present).
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": t("api.error.simulation.m093", i=i + 1)
                }), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m094")
            }), 400

        # Inject the no-tool-call prefix into every interview prompt.
        optimized_interviews = []
        for interview in interviews:
            optimized_interview = interview.copy()
            optimized_interview['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized_interview)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": t("api.error.simulation.m095", str=str(e))
        }), 504

    except Exception as e:
        logger.error(t("log.simulation_api.m096", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """Global interview — ask the same question of every agent.

    Note: requires the simulation environment to be running.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",            // required
            "prompt": "...",                        // required, the same question for every agent
            "platform": "reddit",                   // optional (twitter/reddit)
                                                    //   omit -> dual-platform sims interview each agent on both platforms
            "timeout": 180                          // optional, timeout in seconds, default 180
        }

    Response:
        {
            "success": true,
            "data": {
                "interviews_count": 50,
                "result": {
                    "interviews_count": 100,
                    "results": {
                        "twitter_0": {"agent_id": 0, "response": "...", "platform": "twitter"},
                        "reddit_0": {"agent_id": 0, "response": "...", "platform": "reddit"},
                        ...
                    }
                },
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        prompt = data.get('prompt')
        platform = data.get('platform')  # optional: twitter / reddit / None
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m097")
            }), 400

        if not prompt:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m098")
            }), 400

        if platform and platform not in ("twitter", "reddit"):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m099")
            }), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m100")
            }), 400

        # Inject the no-tool-call prefix into the prompt.
        optimized_prompt = optimize_interview_prompt(prompt)

        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout
        )

        return jsonify({
            "success": result.get("success", False),
            "data": result
        })

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

    except TimeoutError as e:
        return jsonify({
            "success": False,
            "error": t("api.error.simulation.m101", str=str(e))
        }), 504

    except Exception as e:
        logger.error(t("log.simulation_api.m102", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """Return interview history.

    Reads all interview records from the simulation database.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // required
            "platform": "reddit",          // optional (reddit/twitter)
                                           //   omit -> return history for both platforms
            "agent_id": 0,                 // optional, restrict to one agent
            "limit": 100                   // optional, default 100
        }

    Response:
        {
            "success": true,
            "data": {
                "count": 10,
                "history": [
                    {
                        "agent_id": 0,
                        "response": "...",
                        "prompt": "...",
                        "timestamp": "2025-12-08T10:00:00",
                        "platform": "reddit"
                    },
                    ...
                ]
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        platform = data.get('platform')  # When omitted, returns history for both platforms.
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m103")
            }), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": {
                "count": len(history),
                "history": history
            }
        })

    except Exception as e:
        logger.error(t("log.simulation_api.m104", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/env-status', methods=['POST'])
def get_env_status():
    """Return the simulation environment status.

    Checks whether the simulation environment is alive (i.e. able to accept
    interview commands).

    Request (JSON):
        {
            "simulation_id": "sim_xxxx"  // required
        }

    Response:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "env_alive": true,
                "twitter_available": true,
                "reddit_available": true,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m105")
            }), 400

        env_alive = SimulationRunner.check_env_alive(simulation_id)

        env_status = SimulationRunner.get_env_status_detail(simulation_id)

        if env_alive:
            message = t("api.envRunning")
        else:
            message = t("api.envNotRunningShort")

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "env_alive": env_alive,
                "twitter_available": env_status.get("twitter_available", False),
                "reddit_available": env_status.get("reddit_available", False),
                "message": message
            }
        })

    except Exception as e:
        logger.error(t("log.simulation_api.m106", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@simulation_bp.route('/close-env', methods=['POST'])
def close_simulation_env():
    """Close the simulation environment.

    Sends a "close-env" command to the simulation so it can gracefully exit
    command-wait mode.

    Note: this is different from `/stop`, which kills the process. This
    endpoint asks the simulation to shut down its environment cleanly.

    Request (JSON):
        {
            "simulation_id": "sim_xxxx",  // required
            "timeout": 30                  // optional, timeout in seconds, default 30
        }

    Response:
        {
            "success": true,
            "data": {
                "message": "...",
                "result": {...},
                "timestamp": "2025-12-08T10:00:01"
            }
        }
    """
    try:
        data = request.get_json() or {}
        
        simulation_id = data.get('simulation_id')
        timeout = data.get('timeout', 30)
        
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": t("api.error.simulation.m107")
            }), 400
        
        result = SimulationRunner.close_simulation_env(
            simulation_id=simulation_id,
            timeout=timeout
        )
        
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if state:
            state.status = SimulationStatus.COMPLETED
            manager._save_simulation_state(state)
        
        return jsonify({
            "success": result.get("success", False),
            "data": result
        })
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
        
    except Exception as e:
        logger.error(t("log.simulation_api.m108", str=str(e)))
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
