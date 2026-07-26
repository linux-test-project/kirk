"""
.. module:: mcp
    :platform: Linux
    :synopsis: MCP server exposing kirk testing tools

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import importlib.util
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

import libkirk
import libkirk.com
import libkirk.sut
from libkirk.data import (
    Suite,
    Test,
)
from libkirk.ltp import LTPFramework
from libkirk.results import (
    SuiteResults,
    TestResults,
)
from libkirk.session import Session
from libkirk.sut import SUT
from libkirk.tempfile import TempDir

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    pass


@dataclass
class RunState:
    """State of a single test execution run."""

    run_id: str
    task: Optional[asyncio.Task] = None
    status: str = "started"
    tests_total: int = 0
    tests_completed: int = 0
    passed: int = 0
    failed: int = 0
    broken: int = 0
    skipped: int = 0
    warnings: int = 0
    current_suite: str = ""
    results: List[SuiteResults] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class MCPSession:
    """State of a configured SUT session."""

    session_id: str
    sut: SUT
    tmpdir: TempDir
    runs: Dict[str, RunState] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class ProgressTracker:
    """
    Subscribes to kirk events for a specific run and accumulates
    progress counters.
    """

    def __init__(self, run_state: RunState) -> None:
        self._run = run_state
        self._handlers = {}

    async def start(self) -> None:
        async def on_suite_started(suite: Suite) -> None:
            self._run.current_suite = suite.name
            self._run.tests_total += len(suite.tests)
            self._run.status = "running"

        async def on_test_completed(results: TestResults) -> None:
            self._run.tests_completed += 1
            self._run.passed += results.passed
            self._run.failed += results.failed
            self._run.broken += results.broken
            self._run.skipped += results.skipped
            self._run.warnings += results.warnings

        async def on_suite_completed(results: SuiteResults, exec_time: float) -> None:
            self._run.results.append(results)

        self._handlers = {
            "suite_started": on_suite_started,
            "test_completed": on_test_completed,
            "suite_completed": on_suite_completed,
        }

        for name, handler in self._handlers.items():
            libkirk.events.register(name, handler)

    async def stop(self) -> None:
        for name, handler in self._handlers.items():
            libkirk.events.unregister(name, handler)

        self._handlers.clear()


class SessionManager:
    """Manages the mapping from session IDs to MCPSession objects."""

    def __init__(self) -> None:
        self._sessions: Dict[str, MCPSession] = {}

    async def configure(
        self,
        channel_name: str = "shell",
        channel_params: Optional[Dict[str, str]] = None,
        sut_name: str = "default",
        tmp_dir: str = "/tmp",
    ) -> MCPSession:
        channels = libkirk.com.get_channels()
        channel = next((c for c in channels if c.name == channel_name), None)
        if not channel:
            available = [c.name for c in channels]
            raise ValueError(
                f"Channel '{channel_name}' not found. Available: {available}"
            )

        suts = libkirk.sut.get_suts()
        sut = next((s for s in suts if s.name == sut_name), None)
        if not sut:
            available = [s.name for s in suts]
            raise ValueError(f"SUT '{sut_name}' not found. Available: {available}")

        tmpdir = TempDir(tmp_dir)

        config = dict(channel_params or {})
        config["name"] = channel_name
        config["tmpdir"] = tmpdir.abspath
        # pyrefly: ignore[bad-argument-type]
        channel.setup(**config)

        sut_config = {"name": sut_name, "tmpdir": tmpdir.abspath}
        # pyrefly: ignore[bad-argument-type]
        sut.setup(**sut_config)

        session_id = str(uuid.uuid4())[:8]
        mcp_session = MCPSession(
            session_id=session_id,
            sut=sut,
            tmpdir=tmpdir,
        )
        self._sessions[session_id] = mcp_session
        return mcp_session

    def get_session(self, session_id: str) -> MCPSession:
        session = self._sessions.get(session_id)
        if not session:
            available = list(self._sessions.keys())
            raise ValueError(
                f"Session '{session_id}' not found. Active sessions: {available}"
            )
        return session

    async def remove_session(self, session_id: str) -> None:
        session = self.get_session(session_id)

        for run in session.runs.values():
            if run.task and not run.task.done():
                run.task.cancel()

        try:
            sut = session.sut
            if await sut.is_running():
                await sut.stop()
        except Exception:
            pass

        del self._sessions[session_id]

    async def cleanup(self) -> None:
        for sid in list(self._sessions.keys()):
            await self.remove_session(sid)


def _test_to_dict(test: Test) -> Dict[str, Any]:
    return {
        "name": test.name,
        "command": test.command,
        "arguments": test.arguments,
        "parallelizable": test.parallelizable,
    }


def _suite_results_to_dict(
    results: SuiteResults, include_stdout: bool = False
) -> Dict[str, Any]:
    tests = []
    for tres in results.tests_results:
        entry = {
            "name": tres.test.name,
            "status": tres.status,
            "passed": tres.passed,
            "failed": tres.failed,
            "broken": tres.broken,
            "skipped": tres.skipped,
            "warnings": tres.warnings,
            "exec_time": tres.exec_time,
            "return_code": tres.return_code,
        }
        if include_stdout:
            entry["stdout"] = tres.stdout
        tests.append(entry)

    return {
        "suite": results.suite.name,
        "tests": tests,
        "environment": {
            "kernel": results.kernel,
            "arch": results.arch,
            "cpu": results.cpu,
            "ram": results.ram,
            "swap": results.swap,
            "distro": results.distro,
            "distro_ver": results.distro_ver,
        },
    }


_manager = SessionManager()


def _create_mcp_app() -> "FastMCP":
    @asynccontextmanager
    async def _server_lifespan(server: "FastMCP") -> AsyncIterator[None]:
        events_task = asyncio.create_task(libkirk.events.start())
        try:
            yield
        finally:
            await _manager.cleanup()
            await libkirk.events.stop()
            events_task.cancel()
            try:
                await events_task
            except asyncio.CancelledError:
                pass

    app = FastMCP(
        name="kirk",
        instructions="Kirk - Linux Test Project test executor. "
        "Use configure_sut first, then list_suites, run_suite, "
        "get_run_status, and get_results.",
        lifespan=_server_lifespan,
    )

    @app.tool()
    async def configure_sut(
        channel_name: str = "shell",
        channel_params: Optional[Dict[str, str]] = None,
        sut_name: str = "default",
        tmp_dir: str = "/tmp",
    ) -> Dict[str, str]:
        """Configure a System Under Test with a communication channel.

        Args:
            channel_name: Communication channel (shell, ssh, qemu, ltx).
            channel_params: Channel-specific parameters (e.g. host, user, password for ssh).
            sut_name: SUT plugin name.
            tmp_dir: Temporary directory path.

        Returns:
            Session configuration with session_id to use in subsequent calls.
        """
        session = await _manager.configure(
            channel_name=channel_name,
            channel_params=channel_params,
            sut_name=sut_name,
            tmp_dir=tmp_dir,
        )
        return {
            "session_id": session.session_id,
            "sut": sut_name,
            "channel": channel_name,
            "status": "configured",
        }

    @app.tool()
    async def list_suites(session_id: str) -> Dict[str, Any]:
        """List available LTP test suites on the configured SUT.

        Args:
            session_id: Session identifier from configure_sut.

        Returns:
            List of available test suite names.
        """
        session = _manager.get_session(session_id)
        sut = session.sut

        if not await sut.is_running():
            await sut.start()

        channel = sut.get_channel()
        framework = LTPFramework()
        suites = await framework.get_suites(channel)
        return {"suites": suites}

    @app.tool()
    async def run_suite(
        session_id: str,
        suites: List[str],
        skip_tests: Optional[str] = None,
        exec_timeout: int = 3600,
        suite_timeout: int = 3600,
        workers: int = 1,
    ) -> Dict[str, Any]:
        """Execute one or more LTP test suites. Returns immediately with a run_id
        for polling status.

        Args:
            session_id: Session identifier from configure_sut.
            suites: List of test suite names to execute.
            skip_tests: Regex pattern to exclude matching tests.
            exec_timeout: Per-test timeout in seconds (default 3600).
            suite_timeout: Per-suite timeout in seconds (default 3600).
            workers: Number of parallel workers (default 1).

        Returns:
            Run identifier and status.
        """
        mcp_session = _manager.get_session(session_id)

        run_id = str(uuid.uuid4())[:8]
        run_state = RunState(run_id=run_id)

        tracker = ProgressTracker(run_state)
        await tracker.start()

        kirk_session = Session(
            tmpdir=mcp_session.tmpdir,
            sut=mcp_session.sut,
            exec_timeout=float(exec_timeout),
            suite_timeout=float(suite_timeout),
            workers=workers,
        )

        async def execute() -> None:
            try:
                await kirk_session.run(
                    suites=suites,
                    skip_tests=skip_tests,
                )
                run_state.status = "completed"
            except asyncio.CancelledError:
                await kirk_session.stop()
                run_state.status = "cancelled"
            except Exception as err:
                run_state.status = "error"
                run_state.error = str(err)
            finally:
                await tracker.stop()

        task = asyncio.create_task(execute())
        run_state.task = task
        mcp_session.runs[run_id] = run_state

        return {
            "run_id": run_id,
            "status": "started",
            "suites": suites,
            "message": "Execution started. Use get_run_status to monitor progress.",
        }

    @app.tool()
    async def run_command(
        session_id: str,
        command: str,
        exec_timeout: int = 3600,
    ) -> Dict[str, str]:
        """Execute a single command on the SUT. Returns immediately with a run_id
        for polling status.

        Args:
            session_id: Session identifier from configure_sut.
            command: Command to execute.
            exec_timeout: Execution timeout in seconds (default 3600).

        Returns:
            Run identifier and status.
        """
        mcp_session = _manager.get_session(session_id)

        run_id = str(uuid.uuid4())[:8]
        run_state = RunState(run_id=run_id)

        kirk_session = Session(
            tmpdir=mcp_session.tmpdir,
            sut=mcp_session.sut,
            exec_timeout=float(exec_timeout),
        )

        async def execute() -> None:
            try:
                await kirk_session.run(command=command)
                run_state.status = "completed"
            except asyncio.CancelledError:
                await kirk_session.stop()
                run_state.status = "cancelled"
            except Exception as err:
                run_state.status = "error"
                run_state.error = str(err)

        task = asyncio.create_task(execute())
        run_state.task = task
        mcp_session.runs[run_id] = run_state

        return {
            "run_id": run_id,
            "status": "started",
            "command": command,
            "message": "Command execution started. "
            "Use get_run_status to monitor progress.",
        }

    @app.tool()
    async def get_run_status(
        session_id: str,
        run_id: str,
    ) -> Dict[str, Any]:
        """Check the status of a running or completed test execution.

        Args:
            session_id: Session identifier from configure_sut.
            run_id: Run identifier from run_suite or run_command.

        Returns:
            Current status and progress information.
        """
        mcp_session = _manager.get_session(session_id)
        run = mcp_session.runs.get(run_id)
        if not run:
            raise ValueError(
                f"Run '{run_id}' not found. "
                f"Active runs: {list(mcp_session.runs.keys())}"
            )

        result: Dict[str, Any] = {
            "run_id": run_id,
            "status": run.status,
        }

        if run.status in ("started", "running"):
            result["progress"] = {
                "tests_completed": run.tests_completed,
                "tests_total": run.tests_total,
                "current_suite": run.current_suite,
                "passed": run.passed,
                "failed": run.failed,
                "broken": run.broken,
                "skipped": run.skipped,
                "warnings": run.warnings,
            }
        elif run.status == "completed":
            result["summary"] = {
                "passed": run.passed,
                "failed": run.failed,
                "broken": run.broken,
                "skipped": run.skipped,
                "warnings": run.warnings,
            }
        elif run.status == "error":
            result["error"] = run.error

        return result

    @app.tool()
    async def get_results(
        session_id: str,
        run_id: str,
        include_stdout: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve detailed test results for a completed run.

        Args:
            session_id: Session identifier from configure_sut.
            run_id: Run identifier from run_suite.
            include_stdout: Whether to include test stdout in results.

        Returns:
            Detailed per-test results with status and environment info.
        """
        mcp_session = _manager.get_session(session_id)
        run = mcp_session.runs.get(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found")

        if run.status not in ("completed", "error"):
            return {
                "run_id": run_id,
                "status": run.status,
                "message": "Run has not completed yet. "
                "Use get_run_status to check progress.",
            }

        return {
            "run_id": run_id,
            "status": run.status,
            "results": [_suite_results_to_dict(r, include_stdout) for r in run.results],
        }

    @app.tool()
    async def stop_session(session_id: str) -> Dict[str, str]:
        """Stop an active session and release resources.

        Args:
            session_id: Session identifier from configure_sut.

        Returns:
            Confirmation of session teardown.
        """
        await _manager.remove_session(session_id)
        return {"session_id": session_id, "status": "stopped"}

    return app


def start_server() -> None:
    """Entry point for the MCP server, called from main.py when --mcp is used."""
    if not importlib.util.find_spec("mcp"):
        raise RuntimeError("'mcp' library is not available")

    logging.basicConfig(level=logging.INFO)
    app = _create_mcp_app()
    app.run(transport="stdio")
