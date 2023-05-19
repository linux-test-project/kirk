"""
Unittests for the session module.
"""
import json
import asyncio
import pytest
from kirk.host import HostSUT
from kirk.session import Session
from kirk.tempfile import TempDir
from kirk.sut import SUT
from kirk.data import Suite
from kirk.data import Test
from kirk.framework import Framework


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sut_config():
    """
    SUT Configuration.
    """
    yield {}


@pytest.fixture
async def sut(sut_config):
    """
    SUT communication object.
    """
    obj = HostSUT()
    obj.setup(*sut_config)
    await obj.communicate()
    yield obj
    await obj.stop()


class DummyFramework(Framework):
    """
    A generic framework created for testing.
    """

    def __init__(self) -> None:
        self._root = None

    def setup(self, **kwargs: dict) -> None:
        self._root = kwargs.get("root", "/")

    @property
    def name(self) -> str:
        return "dummy"

    async def get_suites(self, sut: SUT) -> list:
        return ["suite01", "suite02", "sleep", "environ", "kernel_panic"]

    async def find_suite(self, sut: SUT, name: str) -> Suite:
        if name in ["suite01", "suite02"]:
            test0 = Test(
                name="test01",
                cwd=self._root,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False)

            test1 = Test(
                name="test02",
                cwd=self._root,
                cmd="sleep",
                args=["0.2", "&&", "echo", "-n", "ciao1"],
                parallelizable=True)

            return Suite(name, [test0, test1])
        elif name in ["sleep"]:
            test0 = Test(
                name="test01",
                cwd=self._root,
                cmd="sleep",
                args=["2"],
                parallelizable=False)

            test1 = Test(
                name="test02",
                cwd=self._root,
                cmd="sleep",
                args=["2"],
                parallelizable=False)

            return Suite(name, [test0, test1])
        elif name in ["environ"]:
            test0 = Test(
                name="test01",
                cwd=self._root,
                cmd="echo",
                args=["-n", "$hello"],
                parallelizable=False)

            return Suite(name, [test0])

        return None


@pytest.fixture
def dummy_framework(tmpdir):
    """
    A fummy framework implementation used for testing.
    """
    obj = DummyFramework()
    obj.setup(root=str(tmpdir))
    yield obj


class TestSession:
    """
    Test for Session class.
    """

    @pytest.fixture
    async def session(self, tmpdir, sut, dummy_framework):
        """
        Session communication object.
        """
        session = Session(
            tmpdir=TempDir(str(tmpdir)),
            frameworks=[dummy_framework],
            sut=sut)

        yield session

        await asyncio.wait_for(session.stop(), timeout=30)

    async def test_run(self, tmpdir, session):
        """
        Test run method when executing suites.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites={"dummy": ["suite01", "suite02"]},
            report_path=report)

        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 4

    async def test_run_skip_tests(self, tmpdir, sut, dummy_framework):
        """
        Test run method when executing suites.
        """
        session = Session(
            tmpdir=TempDir(str(tmpdir)),
            frameworks=[dummy_framework],
            sut=sut,
            skip_tests="test0[12]"
        )

        report = str(tmpdir / "report.json")
        try:
            await session.run(
                suites={"dummy": ["suite01", "suite02"]},
                report_path=report)
        finally:
            await asyncio.wait_for(session.stop(), timeout=30)

        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 0

    async def test_run_stop(self, tmpdir, session):
        """
        Test stop method during run.
        """
        async def stop():
            await asyncio.sleep(0.2)
            await session.stop()

        report = str(tmpdir / "report.json")
        await asyncio.gather(*[
            session.run(suites={"dummy": ["sleep"]}, report_path=report),
            stop(),
        ])

        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 0

    async def test_run_command(self, session):
        """
        Test run method when running a single command.
        """
        await session.run(command="test")

    async def test_run_command_stop(self, tmpdir, dummy_framework, sut):
        """
        Test stop when runnig a command.
        """
        session = Session(
            tmpdir=TempDir(str(tmpdir)),
            frameworks=[dummy_framework],
            sut=sut,
        )

        async def stop():
            await asyncio.sleep(0.1)
            await asyncio.wait_for(session.stop(), timeout=30)

        await asyncio.gather(*[
            session.run(command="sleep 1"),
            stop()
        ])

    async def test_env(self, tmpdir, dummy_framework, sut):
        """
        Test environment variables injected in the SUT by session object.
        """
        session = Session(
            tmpdir=TempDir(str(tmpdir)),
            frameworks=[dummy_framework],
            sut=sut,
            env={"hello": "world"}
        )

        report = tmpdir / "report.json"
        try:
            await session.run(
                suites={"dummy": ["environ"]},
                report_path=report)
        finally:
            await asyncio.wait_for(session.stop(), timeout=30)

        with open(report, 'r') as report_f:
            report_d = json.loads(report_f.read())
            assert len(report_d["results"]) == 1
            assert report_d["results"][0]["test"]["log"] == "world"
