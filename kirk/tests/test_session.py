"""
Unittests for the session module.
"""
import json
import asyncio
import pytest
from kirk.host import HostSUT
from kirk.session import Session
from kirk.tempfile import TempDir


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
