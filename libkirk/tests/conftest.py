"""
Generic stuff for pytest.
"""
import libkirk
import pytest
from libkirk.results import TestResults
from libkirk.sut import SUT
from libkirk.framework import Framework
from libkirk.data import Suite
from libkirk.data import Test


@pytest.fixture(scope="session")
def event_loop():
    """
    Current event loop. Keep it in session scope, otherwise tests which
    will use same coroutines will be associated to different event_loop.
    In this way, pytest-asyncio plugin will work properly.
    """
    loop = libkirk.get_event_loop()

    yield loop

    if not loop.is_closed():
        loop.close()


class DummyFramework(Framework):
    """
    A generic framework created for testing.
    """

    def __init__(self) -> None:
        self._root = None

    def setup(self, **kwargs: dict) -> None:
        self._root = kwargs.get("root", "/")
        self._env = kwargs.get("env", None)

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def config_help(self) -> dict:
        return {}

    async def get_suites(self, sut: SUT) -> list:
        return ["suite01", "suite02", "sleep", "environ", "kernel_panic"]

    async def find_command(self, sut: SUT, command: str) -> Test:
        return Test(name=command, cmd=command)

    async def find_suite(self, sut: SUT, name: str) -> Suite:
        if name in "suite01":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False)

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False)

            return Suite(name, [test0, test1])
        if name == "suite02":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False)

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["0.2", "&&", "echo", "-n", "ciao1"],
                parallelizable=True)

            return Suite(name, [test0, test1])
        elif name == "sleep":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["2"],
                parallelizable=False)

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["2"],
                parallelizable=False)

            return Suite(name, [test0, test1])
        elif name == "environ":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "$hello"],
                parallelizable=False)

            return Suite(name, [test0])
        elif name == "kernel_panic":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["Kernel", "panic"],
                parallelizable=False)

            test1 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["0.2"],
                parallelizable=False)

            return Suite(name, [test0, test1])

        return None

    async def read_result(
            self,
            test: Test,
            stdout: str,
            retcode: int,
            exec_t: float) -> TestResults:
        passed = 0
        failed = 0
        skipped = 0
        broken = 0
        skipped = 0
        warnings = 0
        error = retcode == -1

        if retcode == 0:
            passed = 1
        elif retcode == 4:
            warnings = 1
        elif retcode == 32:
            skipped = 1
        elif not error:
            failed = 1

        if error:
            broken = 1

        result = TestResults(
            test=test,
            passed=passed,
            failed=failed,
            broken=broken,
            skipped=skipped,
            warnings=warnings,
            exec_time=exec_t,
            retcode=retcode,
            stdout=stdout,
        )

        return result


@pytest.fixture
def dummy_framework():
    """
    A fummy framework implementation used for testing.
    """
    obj = DummyFramework()
    obj.setup(root="/tmp")
    yield obj
