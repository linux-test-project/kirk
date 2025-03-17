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

    async def test_run_pattern(self, tmpdir, session):
        """
        Test run method when executing tests filtered out with a pattern.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"],
            pattern="test01|test02",
            report_path=report)

        with open(report, "r", encoding="utf-8") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 4

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

    async def test_run_skip_tests(self, tmpdir, session):
        """
        Test run method when executing suites.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"],
            skip_tests="test0[23]",
            report_path=report)

        with open(report, "r", encoding="utf-8") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == 2

    @pytest.mark.parametrize(
        "iterate,expect",
        [
            (0, 4),
            (1, 4),
            (3, 12),
        ]
    )
    async def test_run_suite_iterate(self, tmpdir, session, iterate, expect):
        """
        Test run method when executing a testing suite multiple times.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"],
            suite_iterate=iterate,
            report_path=report)

        with open(report, "r", encoding="utf-8") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) == expect

    async def test_run_randomize(self, tmpdir, session):
        """
        Test run method when executing shuffled tests.
        """
        num_of_suites = 50

        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01"] * num_of_suites,
            randomize=True,
            report_path=report)

        report_data = None
        with open(report, "r", encoding="utf-8") as report_file:
            report_data = json.loads(report_file.read())

        assert len(report_data["results"]) == 2 * num_of_suites

        tests_names = []
        for test in report_data["results"]:
            tests_names.append(test["test_fqn"])

        assert ["test01", "test02"] * num_of_suites != tests_names

    async def test_run_runtime(self, tmpdir, session):
        """
        Test run method when executing suites for a certain amount of time.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01"],
            runtime=1,
            report_path=report)

        with open(report, "r", encoding="utf-8") as report_file:
            report_data = json.loads(report_file.read())
            assert len(report_data["results"]) >= 2
