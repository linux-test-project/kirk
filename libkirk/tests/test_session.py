"""
Unittests for the session module.
"""
import json
import asyncio
import pytest
from libkirk.session import Session
from libkirk.tempfile import TempDir


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sut():
    """
    SUT communication object.
    """
    raise NotImplementedError()


class _TestSession:
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
            framework=dummy_framework,
            sut=sut)

        yield session

        await asyncio.wait_for(session.stop(), timeout=30)

    async def test_run(self, session):
        """
        Test run method when executing suites.
        """
        await session.run(suites=["suite01", "suite02"])

    async def test_run_report(self, tmpdir, session):
        """
        Test run method when executing suites, generating a report.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"],
            report_path=report)

        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 4

    async def test_run_stop(self, session):
        """
        Test stop method during run. We are not going to generate any results
        file, because we are not even sure some tests will be executed.
        """
        async def stop():
            await asyncio.sleep(0.2)
            await session.stop()

        await asyncio.gather(*[
            session.run(suites=["sleep"]),
            stop(),
        ])

    async def test_run_command(self, session):
        """
        Test run method when running a single command.
        """
        await session.run(command="test")

    async def test_run_command_stop(self, session):
        """
        Test stop when runnig a command.
        """
        async def stop():
            await asyncio.sleep(0.1)
            await asyncio.wait_for(session.stop(), timeout=30)

        await asyncio.gather(*[
            session.run(command="sleep 1"),
            stop()
        ])

    async def test_run_skip_tests(self, tmpdir, sut, dummy_framework):
        """
        Test run method when executing suites.
        """
        session = Session(
            tmpdir=TempDir(str(tmpdir)),
            framework=dummy_framework,
            skip_tests="test0[12]",
            sut=sut)

        report = str(tmpdir / "report.json")
        try:
            await session.run(
                suites=["suite01", "suite02"],
                report_path=report)
        finally:
            await asyncio.wait_for(session.stop(), timeout=5)

        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 0
