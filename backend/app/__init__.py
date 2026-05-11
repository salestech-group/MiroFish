"""MiroFish backend Flask application factory."""

import os
import warnings

# Silence multiprocessing.resource_tracker warnings emitted by some third-party
# libraries (e.g. transformers); must run before those modules are imported.
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger
from .utils.locale import t


def create_app(config_class=Config):
    """Flask application factory."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure JSON encoding so non-ASCII characters render literally
    # rather than as \uXXXX escape sequences. Flask >= 2.3 exposes
    # ``app.json.ensure_ascii``; older versions use ``JSON_AS_ASCII``.
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Configure logging.
    logger = setup_logger('mirofish')

    # Only print startup banners in the reloader child process to avoid
    # double-printing in debug mode.
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info(t("log.bootstrap.m001"))
        logger.info("=" * 50)

    # Enable CORS.
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register simulation-process cleanup so all child processes are torn down
    # when the Flask server shuts down.
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info(t("log.bootstrap.m002"))

    # Request-logging middleware.
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(t("log.bootstrap.m003", request=request.method, request_2=request.path))
        if request.content_type and 'json' in request.content_type:
            logger.debug(t("log.bootstrap.m004", request=request.get_json(silent=True)))

    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(t("log.bootstrap.m005", response=response.status_code))
        return response

    # Register API blueprints.
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')

    # Health-check endpoint.
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}

    # On startup: recover any projects stuck in graph_building (task was killed by restart)
    if should_log_startup:
        _recover_stuck_projects()

    if should_log_startup:
        logger.info(t("log.bootstrap.m006"))

    return app


def _recover_stuck_projects():
    """Mark graph_building projects as completed if Neo4j already has their data."""
    from .models.project import ProjectManager, ProjectStatus
    from .utils.logger import get_logger as _get_logger
    _log = _get_logger('mirofish.startup')
    try:
        for p in ProjectManager.list_projects():
            if p.status == ProjectStatus.GRAPH_BUILDING and p.graph_id:
                from .services.graphiti_adapter import _get_graphiti, _run, _neo4j_query
                g = _get_graphiti()
                r = _run(_neo4j_query(g,
                    'MATCH (n:Entity {group_id: $gid}) RETURN count(n) AS n',
                    {'gid': p.graph_id}
                ))
                node_count = int(r[0]['n']) if r else 0
                if node_count > 0:
                    p.status = ProjectStatus.GRAPH_COMPLETED
                    p.graph_build_task_id = None
                    ProjectManager.save_project(p)
                    _log.info(f"Recovered stuck project {p.project_id}: {node_count} nodes found, marked graph_completed")
    except Exception as e:
        _get_logger('mirofish.startup').warning(f"Startup recovery failed: {e}")

