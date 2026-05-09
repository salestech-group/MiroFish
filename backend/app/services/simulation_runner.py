"""
OASIS simulation runner.

Runs the simulation in the background, records each agent's actions, and supports real-time status monitoring.
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from ..utils.locale import get_locale, set_locale, t
from .zep_graph_memory_updater import ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse

logger = get_logger('mirofish.simulation_runner')

# Tracks whether the cleanup handler has been registered (guards against double registration in Flask reloader).
_cleanup_registered = False

IS_WINDOWS = sys.platform == 'win32'


class RunnerStatus(str, Enum):
    """Runner lifecycle states."""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentAction:
    """A single recorded agent action."""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """Per-round summary statistics."""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """Live runtime state for a simulation."""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE

    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: int = 0
    total_simulation_hours: int = 0

    # Per-platform round and simulated-time counters (used when both platforms run in parallel).
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: int = 0
    reddit_simulated_hours: int = 0

    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0

    # Per-platform completion flags, set when a simulation_end event is observed in actions.jsonl.
    twitter_completed: bool = False
    reddit_completed: bool = False

    rounds: List[RoundSummary] = field(default_factory=list)

    # Recent actions buffer; surfaced to the frontend for the live feed.
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50

    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    error: Optional[str] = None

    # Main subprocess PID — captured so the process can later be stopped.
    process_pid: Optional[int] = None

    def add_action(self, action: AgentAction):
        """Prepend an action to the recent-actions buffer and update counters."""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]
        
        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1
        
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # Per-platform round and simulated-time counters.
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """Return the dict form of the state including recent actions."""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    Simulation runner.

    Responsibilities:
    1. Run the OASIS simulation in a background subprocess.
    2. Parse the run logs and record each agent's actions.
    3. Provide real-time status query interfaces.
    4. Support pause/stop/resume operations.
    """

    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )

    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )

    # In-memory caches of runtime state, processes, queues, monitor threads, and log file handles.
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}
    _stderr_files: Dict[str, Any] = {}

    # Graph-memory-update flag per simulation_id.
    _graph_memory_enabled: Dict[str, bool] = {}

    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Return the cached run state, falling back to disk if not loaded yet."""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]

        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state

    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Load run state from the on-disk JSON snapshot."""
        state_file = os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # Per-platform round and simulated-time counters.
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )
            
            # Restore the recent-actions buffer.
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))
            
            return state
        except Exception as e:
            logger.error(t("log.simulation_runner.m001", str=str(e)))
            return None
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """Persist the run state to its JSON snapshot file."""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")
        
        data = state.to_detail_dict()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # Optional cap on simulation rounds (truncates overly long runs).
        enable_graph_memory_update: bool = False,  # Whether to push activity into the Zep graph.
        graph_id: str = None  # Zep graph ID (required when graph-memory updates are enabled).
    ) -> SimulationRunState:
        """
        Start the simulation.

        Args:
            simulation_id: Simulation ID.
            platform: Platform to run (twitter/reddit/parallel).
            max_rounds: Optional cap on simulation rounds (truncates overly long runs).
            enable_graph_memory_update: Whether to push agent activity to the Zep graph in real time.
            graph_id: Zep graph ID (required when graph-memory updates are enabled).

        Returns:
            SimulationRunState
        """
        # Refuse to start a duplicate run for the same simulation_id.
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"模拟已在运行中: {simulation_id}")
        
        # Load the simulation configuration written during preparation.
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            raise ValueError(f"模拟配置不存在，请先调用 /prepare 接口")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Compute total rounds from time-window settings.
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # If a cap was provided, clamp total_rounds.
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(t("log.simulation_runner.m002", original_rounds=original_rounds, total_rounds=total_rounds, max_rounds=max_rounds))
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        cls._save_run_state(state)
        
        # Spin up a graph-memory updater if requested.
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("启用图谱记忆更新时必须提供 graph_id")
            
            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(t("log.simulation_runner.m003", simulation_id=simulation_id, graph_id=graph_id))
            except Exception as e:
                logger.error(t("log.simulation_runner.m004", e=e))
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # Pick the entry script (lives in backend/scripts/) based on the requested platform.
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            raise ValueError(f"脚本不存在: {script_path}")
        
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue

        try:
            # Log layout written by the subprocess:
            #   twitter/actions.jsonl - Twitter action log
            #   reddit/actions.jsonl  - Reddit action log
            #   simulation.log        - main-process log

            cmd = [
                sys.executable,
                script_path,
                "--config", config_path,
            ]

            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])

            # Redirect stdout/stderr to a file so a full pipe buffer cannot block the subprocess.
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')

            # Force UTF-8 in the child so third-party libs (e.g. OASIS) that open files without an
            # explicit encoding work correctly on Windows.
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'
            env['PYTHONIOENCODING'] = 'utf-8'

            # cwd is the simulation directory so generated artifacts (databases, etc.) land there.
            # start_new_session=True creates a fresh process group so os.killpg can terminate the
            # entire tree on shutdown.
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                env=env,
                start_new_session=True,
            )

            # Retain the log file handle so it can be closed after the subprocess exits.
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None
            
            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)
            
            # Capture locale before spawning monitor thread
            current_locale = get_locale()

            # Spawn the log-tailing monitor thread.
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id, current_locale),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread
            
            logger.info(t("log.simulation_runner.m005", simulation_id=simulation_id, process=process.pid, platform=platform))
            
        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str, locale: str = 'zh'):
        """Monitor the simulation process and tail its per-platform action logs."""
        set_locale(locale)
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)
        
        if not process or not state:
            return
        
        twitter_position = 0
        reddit_position = 0
        
        try:
            while process.poll() is None:
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )

                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )

                cls._save_run_state(state)
                time.sleep(2)

            # Drain any log lines written between the last poll and the process exit.
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")

            exit_code = process.returncode
            
            if exit_code == 0:
                state.runner_status = RunnerStatus.COMPLETED
                state.completed_at = datetime.now().isoformat()
                logger.info(t("log.simulation_runner.m006", simulation_id=simulation_id))
            else:
                state.runner_status = RunnerStatus.FAILED
                # Pull the tail of the main log so the failure context is surfaced in state.error.
                main_log_path = os.path.join(sim_dir, "simulation.log")
                error_info = ""
                try:
                    if os.path.exists(main_log_path):
                        with open(main_log_path, 'r', encoding='utf-8') as f:
                            error_info = f.read()[-2000:]  # keep only the last 2000 chars
                except Exception:
                    pass
                state.error = f"进程退出码: {exit_code}, 错误: {error_info}"
                logger.error(t("log.simulation_runner.m007", simulation_id=simulation_id, state=state.error))
            
            state.twitter_running = False
            state.reddit_running = False
            cls._save_run_state(state)
            
        except Exception as e:
            logger.error(t("log.simulation_runner.m008", simulation_id=simulation_id, str=str(e)))
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
        
        finally:
            # Tear down the graph-memory updater, if we started one.
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    logger.info(t("log.simulation_runner.m009", simulation_id=simulation_id))
                except Exception as e:
                    logger.error(t("log.simulation_runner.m010", e=e))
                cls._graph_memory_enabled.pop(simulation_id, None)

            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)

            # Close the retained log file handles.
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)
    
    @classmethod
    def _read_action_log(
        cls, 
        log_path: str, 
        position: int, 
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        Read new entries from a per-platform action log.

        Args:
            log_path: Path to the action-log file.
            position: Byte offset where the previous read finished.
            state: Run-state object to mutate.
            platform: Platform name (twitter/reddit).

        Returns:
            New byte offset after this read.
        """
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)

                            # Event records (simulation_start/end, round_end, ...) are routed here.
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")

                                # simulation_end means the platform finished its run.
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(t("log.simulation_runner.m011", state=state.simulation_id, action_data=action_data.get('total_rounds'), action_data_2=action_data.get('total_actions')))
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(t("log.simulation_runner.m012", state=state.simulation_id, action_data=action_data.get('total_rounds'), action_data_2=action_data.get('total_actions')))
                                    
                                    # Mark the run as completed once every enabled platform has reported
                                    # simulation_end. Single-platform runs only need that one.
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(t("log.simulation_runner.m013", state=state.simulation_id))
                                
                                # Round counters come from round_end events.
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)

                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours

                                    # Overall counters track the max across enabled platforms.
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)

                                continue
                            
                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)

                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num

                            # Forward the activity to the Zep graph when the updater is enabled.
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)
                            
                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(t("log.simulation_runner.m014", log_path=log_path, e=e))
            return position
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        Return whether every enabled platform has completed its simulation.

        A platform counts as enabled when its corresponding actions.jsonl file exists on disk.

        Returns:
            True if all enabled platforms have completed.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")

        # File presence is our enabled-platform signal.
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)

        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False

        # At least one platform must be enabled (and, by the checks above, completed).
        return twitter_enabled or reddit_enabled
    
    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        Terminate a process and its subprocesses in a cross-platform way.

        Args:
            process: Process to terminate.
            simulation_id: Simulation ID (used for log messages).
            timeout: Seconds to wait for graceful exit before escalating.
        """
        if IS_WINDOWS:
            # Windows: taskkill /T tears down the whole process tree, /F escalates to a hard kill.
            logger.info(t("log.simulation_runner.m015", simulation_id=simulation_id, process=process.pid))
            try:
                # Graceful termination first.
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Force kill the tree.
                    logger.warning(t("log.simulation_runner.m016", simulation_id=simulation_id))
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(t("log.simulation_runner.m017", e=e))
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: kill the entire process group.
            # Because the subprocess was started with start_new_session=True the pgid equals the PID.
            pgid = os.getpgid(process.pid)
            logger.info(t("log.simulation_runner.m018", simulation_id=simulation_id, pgid=pgid))

            # SIGTERM first to allow graceful shutdown.
            os.killpg(pgid, signal.SIGTERM)

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Escalate to SIGKILL on timeout.
                logger.warning(t("log.simulation_runner.m019", simulation_id=simulation_id))
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Stop the simulation subprocess and update its state."""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"模拟不存在: {simulation_id}")
        
        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"模拟未在运行: {simulation_id}, status={state.runner_status}")
        
        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)
        
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # The process has already exited.
                pass
            except Exception as e:
                logger.error(t("log.simulation_runner.m020", simulation_id=simulation_id, e=e))
                # Fall back to direct termination on the Popen handle.
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        
        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)

        # Tear down the graph-memory updater, if any.
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                logger.info(t("log.simulation_runner.m021", simulation_id=simulation_id))
            except Exception as e:
                logger.error(t("log.simulation_runner.m022", e=e))
            cls._graph_memory_enabled.pop(simulation_id, None)
        
        logger.info(t("log.simulation_runner.m023", simulation_id=simulation_id))
        return state
    
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Read actions from a single action-log file.

        Args:
            file_path: Path to the action-log file.
            default_platform: Platform to assume when a record has no `platform` field.
            platform_filter: Optional platform filter.
            agent_id: Optional agent-id filter.
            round_num: Optional round-number filter.
        """
        if not os.path.exists(file_path):
            return []
        
        actions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)

                    # Skip event records (simulation_start, round_start, round_end, ...).
                    if "event_type" in data:
                        continue

                    # Skip records without an agent_id (non-agent actions).
                    if "agent_id" not in data:
                        continue

                    # Prefer the record's own platform; fall back to the default for legacy entries.
                    record_platform = data.get("platform") or default_platform or ""

                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue
                    
                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))
                    
                except json.JSONDecodeError:
                    continue
        
        return actions
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Return the complete action history across all platforms (no pagination).

        Args:
            simulation_id: Simulation ID.
            platform: Optional platform filter (twitter/reddit).
            agent_id: Optional agent filter.
            round_num: Optional round filter.

        Returns:
            Full action list, sorted by timestamp with newest first.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        actions = []

        # Twitter action log: derive platform from the file path.
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))

        # Reddit action log: derive platform from the file path.
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))

        # Fall back to the legacy single-file layout if no per-platform files exist.
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # Legacy files carry their own platform field.
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )

        # Newest-first by timestamp.
        actions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return actions
    
    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Return action history with pagination.

        Args:
            simulation_id: Simulation ID.
            limit: Maximum number of actions to return.
            offset: Offset into the sorted result list.
            platform: Optional platform filter.
            agent_id: Optional agent filter.
            round_num: Optional round filter.

        Returns:
            A page of actions.
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )

        return actions[offset:offset + limit]
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Return a per-round timeline summary for the simulation.

        Args:
            simulation_id: Simulation ID.
            start_round: First round to include (inclusive).
            end_round: Last round to include (inclusive); None means no upper bound.

        Returns:
            One summary entry per round.
        """
        actions = cls.get_actions(simulation_id, limit=10000)

        # Group actions by round.
        rounds: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            round_num = action.round_num
            
            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue
            
            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            r = rounds[round_num]
            
            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1
            
            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp
        
        # Materialise into a sorted list.
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })
        
        return result
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Return per-agent statistics for the simulation.

        Returns:
            Per-agent statistics, sorted by total action count (descending).
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        agent_stats: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            agent_id = action.agent_id
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            stats = agent_stats[agent_id]
            stats["total_actions"] += 1
            
            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1
            
            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp
        
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
        
        return result
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Clean up the simulation's run logs so the simulation can be force-restarted.

        Deletes the following files:
        - run_state.json
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db (simulation database)
        - reddit_simulation.db (simulation database)
        - env_status.json (environment status)

        Note: simulation_config.json and the profile files are preserved.

        Args:
            simulation_id: Simulation ID.

        Returns:
            Cleanup result info.
        """
        import shutil
        
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return {"success": True, "message": "模拟目录不存在，无需清理"}
        
        cleaned_files = []
        errors = []
        
        # Files to delete (includes per-platform databases).
        files_to_delete = [
            "run_state.json",
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Twitter platform database.
            "reddit_simulation.db",   # Reddit platform database.
            "env_status.json",        # Environment-status file.
        ]

        # Per-platform directories whose action logs should be cleaned.
        dirs_to_clean = ["twitter", "reddit"]

        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"删除 {filename} 失败: {str(e)}")

        # Clean per-platform action logs.
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"删除 {dir_name}/actions.jsonl 失败: {str(e)}")
        
        # Drop the in-memory run state for this simulation.
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]
        
        logger.info(t("log.simulation_runner.m024", simulation_id=simulation_id, cleaned_files=cleaned_files))
        
        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None
        }
    
    # Guard so cleanup_all_simulations only runs once per process lifetime.
    _cleanup_done = False

    @classmethod
    def cleanup_all_simulations(cls):
        """
        Clean up every running simulation subprocess.

        Invoked at server shutdown to guarantee no child processes leak.
        """
        if cls._cleanup_done:
            return
        cls._cleanup_done = True

        # Skip the "shutting down" log entirely if there's nothing to clean up.
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)

        if not has_processes and not has_updaters:
            return

        logger.info(t("log.simulation_runner.m025"))

        # Stop graph-memory updaters first (stop_all logs internally).
        try:
            ZepGraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(t("log.simulation_runner.m026", e=e))
        cls._graph_memory_enabled.clear()

        # Snapshot the process map so we can mutate it during iteration.
        processes = list(cls._processes.items())

        for simulation_id, process in processes:
            try:
                if process.poll() is None:
                    logger.info(t("log.simulation_runner.m027", simulation_id=simulation_id, process=process.pid))

                    try:
                        cls._terminate_process(process, simulation_id, timeout=5)
                    except (ProcessLookupError, OSError):
                        # The process may already be gone; fall back to direct termination.
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()

                    # Update run_state.json so external readers see the stopped status.
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "服务器关闭，模拟被终止"
                        cls._save_run_state(state)
                    
                    # Also flip the project-level state.json status to "stopped".
                    try:
                        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                        state_file = os.path.join(sim_dir, "state.json")
                        logger.info(t("log.simulation_runner.m028", state_file=state_file))
                        if os.path.exists(state_file):
                            with open(state_file, 'r', encoding='utf-8') as f:
                                state_data = json.load(f)
                            state_data['status'] = 'stopped'
                            state_data['updated_at'] = datetime.now().isoformat()
                            with open(state_file, 'w', encoding='utf-8') as f:
                                json.dump(state_data, f, indent=2, ensure_ascii=False)
                            logger.info(t("log.simulation_runner.m029", simulation_id=simulation_id))
                        else:
                            logger.warning(t("log.simulation_runner.m030", state_file=state_file))
                    except Exception as state_err:
                        logger.warning(t("log.simulation_runner.m031", simulation_id=simulation_id, state_err=state_err))
                        
            except Exception as e:
                logger.error(t("log.simulation_runner.m032", simulation_id=simulation_id, e=e))
        
        # Close any retained log file handles.
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        
        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()
        
        # Drop in-memory bookkeeping.
        cls._processes.clear()
        cls._action_queues.clear()
        
        logger.info(t("log.simulation_runner.m033"))
    
    @classmethod
    def register_cleanup(cls):
        """
        Register the shutdown cleanup hook.

        Called at Flask application startup so that all simulation subprocesses are torn down
        when the server stops.
        """
        global _cleanup_registered

        if _cleanup_registered:
            return

        # In Flask debug mode the reloader spawns a child process that actually runs the app
        # (signaled by WERKZEUG_RUN_MAIN=true). Outside debug mode that variable is unset and we
        # still want to register the cleanup hook.
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None

        # Debug mode: only register inside the reloader child. Non-debug: always register.
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # Prevent the parent process from retrying.
            return

        # Capture the previously installed signal handlers so we can chain to them.
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP exists only on Unix (macOS/Linux); Windows does not have it.
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)

        def cleanup_handler(signum=None, frame=None):
            """Signal handler that cleans up simulations before delegating to the original handler."""
            # Only log when there is actually something to clean up.
            if cls._processes or cls._graph_memory_enabled:
                logger.info(t("log.simulation_runner.m034", signum=signum))
            cls.cleanup_all_simulations()

            # Chain to the original handler so Flask exits normally.
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP is sent when the terminal is closed.
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # Default behavior: exit cleanly.
                    sys.exit(0)
            else:
                # If the original handler is not callable (e.g. SIG_DFL), use the default behavior.
                raise KeyboardInterrupt

        # Register the atexit handler as a fallback.
        atexit.register(cls.cleanup_all_simulations)

        # Register signal handlers (only valid from the main thread).
        try:
            # SIGTERM: default signal sent by `kill`.
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: terminal close (Unix only).
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # Not the main thread — fall back to the atexit hook.
            logger.warning(t("log.simulation_runner.m035"))

        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """Return a list of every simulation ID with a live subprocess."""
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Interview feature ==============

    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        Check whether the simulation environment is alive and able to receive interview commands.

        Args:
            simulation_id: Simulation ID.

        Returns:
            True if the environment is alive, False if it has shut down.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Return detailed status info for the simulation environment.

        Args:
            simulation_id: Simulation ID.

        Returns:
            Status dict containing status, twitter_available, reddit_available, timestamp.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")
        
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }
        
        if not os.path.exists(status_file):
            return default_status
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Interview a single agent.

        Args:
            simulation_id: Simulation ID.
            agent_id: Agent ID.
            prompt: Interview question.
            platform: Optional platform selector.
                - "twitter": only interview the agent on Twitter.
                - "reddit": only interview the agent on Reddit.
                - None: in dual-platform runs, interview both platforms and return a merged result.
            timeout: Timeout in seconds.

        Returns:
            Interview result dict.

        Raises:
            ValueError: Simulation does not exist or its environment is not running.
            TimeoutError: Timed out waiting for the response.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}")

        logger.info(t("log.simulation_runner.m036", simulation_id=simulation_id, agent_id=agent_id, platform=platform))

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Interview multiple agents in batch.

        Args:
            simulation_id: Simulation ID.
            interviews: Interview list; each entry is {"agent_id": int, "prompt": str, "platform": str (optional)}.
            platform: Optional default platform (overridden per-interview by an entry's own `platform`).
                - "twitter": default to interviewing only Twitter.
                - "reddit": default to interviewing only Reddit.
                - None: in dual-platform runs, interview every agent on both platforms.
            timeout: Timeout in seconds.

        Returns:
            Batch interview result dict.

        Raises:
            ValueError: Simulation does not exist or its environment is not running.
            TimeoutError: Timed out waiting for the response.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"模拟环境未运行或已关闭，无法执行Interview: {simulation_id}")

        logger.info(t("log.simulation_runner.m037", simulation_id=simulation_id, len=len(interviews), platform=platform))

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        Interview every agent in the simulation (global interview).

        Sends the same prompt to every agent in the simulation.

        Args:
            simulation_id: Simulation ID.
            prompt: Interview question used for every agent.
            platform: Optional platform selector.
                - "twitter": only interview Twitter.
                - "reddit": only interview Reddit.
                - None: in dual-platform runs, interview every agent on both platforms.
            timeout: Timeout in seconds.

        Returns:
            Global interview result dict.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")

        # Read every agent from the simulation config.
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"模拟配置不存在: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"模拟配置中没有Agent: {simulation_id}")

        # Build the batch-interview payload.
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(t("log.simulation_runner.m038", simulation_id=simulation_id, len=len(interviews), platform=platform))

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Close the simulation environment (does not stop the simulation subprocess).

        Sends a close-environment command to the simulation so it exits its wait-for-command mode
        gracefully.

        Args:
            simulation_id: Simulation ID.
            timeout: Timeout in seconds.

        Returns:
            Operation-result dict.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"模拟不存在: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "环境已经关闭"
            }
        
        logger.info(t("log.simulation_runner.m039", simulation_id=simulation_id))
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "环境关闭命令已发送",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # Timing out can simply mean the environment is already shutting down.
            return {
                "success": True,
                "message": "环境关闭命令已发送（等待响应超时，环境可能正在关闭）"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Read the interview history from a single per-platform database."""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(t("log.simulation_runner.m040", platform_name=platform_name, e=e))
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Return the interview history (read from the per-platform databases).

        Args:
            simulation_id: Simulation ID.
            platform: Platform selector (reddit/twitter/None).
                - "reddit": only return Reddit history.
                - "twitter": only return Twitter history.
                - None: return history from both platforms.
            agent_id: Optional agent-id filter; if set, only that agent's history is returned.
            limit: Max number of records per platform.

        Returns:
            Interview-history list.
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)

        results = []

        # Decide which platform databases to query.
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # No platform specified: query both.
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # Newest-first by timestamp.
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # When multiple platforms were queried, cap the merged result size.
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results

