"""
Unittests for the MCP server module.
"""

import asyncio

import pytest

mcp_pkg = pytest.importorskip("mcp")

pytestmark = pytest.mark.mcp

import libkirk
from libkirk.data import Suite, Test
from libkirk.mcp_server import (
    ProgressTracker,
    RunState,
    SessionManager,
    _suite_results_to_dict,
    _test_to_dict,
)
from libkirk.results import SuiteResults, TestResults


@pytest.fixture
def manager():
    return SessionManager()


class TestTestToDict:
    def test_basic(self):
        test = Test(name="test01", cmd="echo", args=["-n", "hi"])
        result = _test_to_dict(test)
        assert result["name"] == "test01"
        assert result["command"] == "echo"
        assert result["arguments"] == ["-n", "hi"]
        assert result["parallelizable"] is False


class TestSuiteResultsToDict:
    def test_basic(self):
        test = Test(name="test01", cmd="echo")
        tres = TestResults(
            test=test,
            passed=1,
            failed=0,
            broken=0,
            skipped=0,
            warnings=0,
            exec_time=0.5,
            retcode=0,
            stdout="hello",
        )
        suite = Suite("math", [test])
        sresults = SuiteResults(
            suite=suite,
            tests=[tres],
            distro="opensuse",
            distro_ver="16.0",
            kernel="6.12.0",
            arch="x86_64",
            cpu="x86_64",
            ram="8192",
            swap="2048",
        )

        result = _suite_results_to_dict(sresults)
        assert result["suite"] == "math"
        assert len(result["tests"]) == 1
        assert result["tests"][0]["name"] == "test01"
        assert result["tests"][0]["status"] == 0
        assert "stdout" not in result["tests"][0]
        assert result["environment"]["kernel"] == "6.12.0"

    def test_include_stdout(self):
        test = Test(name="test01", cmd="echo")
        tres = TestResults(
            test=test,
            passed=1,
            failed=0,
            broken=0,
            skipped=0,
            warnings=0,
            exec_time=0.1,
            retcode=0,
            stdout="output",
        )
        suite = Suite("math", [test])
        sresults = SuiteResults(
            suite=suite,
            tests=[tres],
        )

        result = _suite_results_to_dict(sresults, include_stdout=True)
        assert result["tests"][0]["stdout"] == "output"


class TestSessionManager:
    async def test_configure_default(self, manager):
        session = await manager.configure()
        assert session.session_id
        assert session.sut is not None
        assert session.tmpdir is not None

    async def test_configure_invalid_channel(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.configure(channel_name="nonexistent")

    async def test_configure_invalid_sut(self, manager):
        with pytest.raises(ValueError, match="not found"):
            await manager.configure(sut_name="nonexistent")

    async def test_get_session(self, manager):
        session = await manager.configure()
        retrieved = manager.get_session(session.session_id)
        assert retrieved is session

    async def test_get_session_not_found(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.get_session("invalid_id")

    async def test_remove_session(self, manager):
        session = await manager.configure()
        sid = session.session_id
        await manager.remove_session(sid)
        with pytest.raises(ValueError):
            manager.get_session(sid)

    async def test_cleanup(self, manager):
        s1 = await manager.configure()
        s2 = await manager.configure()
        await manager.cleanup()
        with pytest.raises(ValueError):
            manager.get_session(s1.session_id)
        with pytest.raises(ValueError):
            manager.get_session(s2.session_id)


class TestProgressTracker:
    @pytest.fixture(autouse=True)
    async def run_events(self):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())
        yield
        await libkirk.events.stop()

    async def test_suite_started(self):
        run_state = RunState(run_id="r1", task=None)
        tracker = ProgressTracker(run_state)

        await tracker.start()
        try:
            suite = Suite("math", [
                Test(name="t1", cmd="echo"),
                Test(name="t2", cmd="echo"),
            ])
            await libkirk.events.fire("suite_started", suite)
            await self._wait_for(lambda: run_state.status == "running")

            assert run_state.tests_total == 2
            assert run_state.current_suite == "math"
        finally:
            await tracker.stop()

    async def test_test_completed(self):
        run_state = RunState(run_id="r1", task=None)
        tracker = ProgressTracker(run_state)

        await tracker.start()
        try:
            test = Test(name="t1", cmd="echo")
            tres = TestResults(
                test=test,
                passed=1,
                failed=0,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=0.1,
                retcode=0,
                stdout="",
            )
            await libkirk.events.fire("test_completed", tres)
            await self._wait_for(lambda: run_state.tests_completed == 1)

            assert run_state.passed == 1
        finally:
            await tracker.stop()

    async def test_suite_completed(self):
        run_state = RunState(run_id="r1", task=None)
        tracker = ProgressTracker(run_state)

        await tracker.start()
        try:
            test = Test(name="t1", cmd="echo")
            suite = Suite("math", [test])
            sresults = SuiteResults(suite=suite, tests=[])

            await libkirk.events.fire("suite_completed", sresults, 1.0)
            await self._wait_for(lambda: len(run_state.results) == 1)

            assert run_state.results[0].suite.name == "math"
        finally:
            await tracker.stop()

    @staticmethod
    async def _wait_for(condition, timeout=5.0):
        elapsed = 0.0
        while not condition():
            await asyncio.sleep(0.05)
            elapsed += 0.05
            if elapsed >= timeout:
                raise TimeoutError("Condition not met")
