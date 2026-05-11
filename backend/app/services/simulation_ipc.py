"""Simulation IPC module.

Inter-process communication between the Flask backend and the simulation
subprocess. Implements a simple file-system command/response pattern:

1. Flask writes commands into ``commands/``.
2. The simulation script polls for commands, executes them, and writes
   responses into ``responses/``.
3. Flask polls the responses directory for results.
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger
from ..utils.locale import t

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """IPC command types."""
    INTERVIEW = "interview"           # interview a single agent
    BATCH_INTERVIEW = "batch_interview"  # interview multiple agents at once
    CLOSE_ENV = "close_env"           # tear down the environment


class CommandStatus(str, Enum):
    """IPC command status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """A command sent over the IPC channel."""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """A response returned over the IPC channel."""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """IPC client used by the Flask side.

    Sends commands to the simulation process and waits for responses.
    """

    def __init__(self, simulation_dir: str):
        """Initialize the IPC client.

        Args:
            simulation_dir: Directory holding the simulation's IPC files.
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Ensure both directories exist before use.
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """Send a command and wait for the response.

        Args:
            command_type: Command type to send.
            args: Command arguments.
            timeout: Timeout in seconds.
            poll_interval: Polling interval in seconds.

        Returns:
            The ``IPCResponse``.

        Raises:
            TimeoutError: When no response arrives before ``timeout``.
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )

        # Write the command file.
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(t("log.simulation_ipc.m001", command_type=command_type.value, command_id=command_id))

        # Poll for the response file.
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)

                    # Clean up command and response files after successful read.
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass

                    logger.info(t("log.simulation_ipc.m002", command_id=command_id, response=response.status.value))
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(t("log.simulation_ipc.m003", e=e))

            time.sleep(poll_interval)

        # Timed out waiting for the response.
        logger.error(t("log.simulation_ipc.m004", command_id=command_id))

        # Clean up the unanswered command file.
        try:
            os.remove(command_file)
        except OSError:
            pass

        raise TimeoutError(f"等待命令响应超时 ({timeout}秒)")

    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """Send a single-agent interview command.

        Args:
            agent_id: Agent id to interview.
            prompt: Interview question.
            platform: Optional platform selector.
                - ``"twitter"``: interview only on Twitter.
                - ``"reddit"``: interview only on Reddit.
                - ``None``: dual-platform if applicable, else the single active platform.
            timeout: Timeout in seconds.

        Returns:
            ``IPCResponse`` whose ``result`` carries the interview response.
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """Send a batched interview command.

        Args:
            interviews: List of items shaped ``{"agent_id": int, "prompt": str, "platform": str?}``.
            platform: Default platform; per-item ``platform`` overrides this.
                - ``"twitter"``: default to Twitter.
                - ``"reddit"``: default to Reddit.
                - ``None``: dual-platform interview when applicable.
            timeout: Timeout in seconds.

        Returns:
            ``IPCResponse`` whose ``result`` carries every interview response.
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform

        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """Send a tear-down-environment command.

        Args:
            timeout: Timeout in seconds.

        Returns:
            ``IPCResponse``.
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )

    def check_env_alive(self) -> bool:
        """Return ``True`` if the simulation environment reports as alive.

        Reads ``env_status.json`` written by the IPC server side.
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False

        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """IPC server used by the simulation script.

    Polls the commands directory, executes commands, and writes responses.
    """

    def __init__(self, simulation_dir: str):
        """Initialize the IPC server.

        Args:
            simulation_dir: Directory holding the simulation's IPC files.
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")

        # Ensure both directories exist before use.
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

        # Server-running flag.
        self._running = False

    def start(self):
        """Mark the server as alive and persist the state."""
        self._running = True
        self._update_env_status("alive")

    def stop(self):
        """Mark the server as stopped and persist the state."""
        self._running = False
        self._update_env_status("stopped")

    def _update_env_status(self, status: str):
        """Update the persistent environment-status file."""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def poll_commands(self) -> Optional[IPCCommand]:
        """Poll the commands directory and return the next pending command.

        Returns:
            ``IPCCommand`` or ``None`` if no pending commands remain.
        """
        if not os.path.exists(self.commands_dir):
            return None

        # Sort by mtime so we process commands in arrival order.
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))

        command_files.sort(key=lambda x: x[1])

        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(t("log.simulation_ipc.m005", filepath=filepath, e=e))
                continue

        return None

    def send_response(self, response: IPCResponse):
        """Write a response file.

        Args:
            response: The response to send.
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)

        # Delete the matching command file.
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass

    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Send a success response."""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))

    def send_error(self, command_id: str, error: str):
        """Send a failure response."""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
