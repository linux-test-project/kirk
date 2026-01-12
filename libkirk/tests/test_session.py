"""
Unittests for the session module.
"""

import os
import json
import pathlib
import asyncio
from typing import List

import pytest

from libkirk.ltp import LTPFramework
from libkirk.com import ComChannel
from libkirk.data import Test, Suite
from libkirk.results import TestResults
from libkirk.session import Session
from libkirk.tempfile import TempDir


@pytest.fixture
async def sut():
    """
    SUT communication object.
    """
    raise NotImplementedError()


class DummyFramework(LTPFramework):
    """
    A generic framework created for testing.
    """

    async def get_suites(self, channel: ComChannel) -> List[str]:
        return ["suite01", "suite02", "sleep", "environ", "kernel_panic"]

    async def find_command(self, channel: ComChannel, command: str) -> Test:
        return Test(name=command, cmd=command)

    async def find_suite(self, channel: ComChannel, name: str) -> Suite:
        if name in "suite01":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False,
            )

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False,
            )

            return Suite(name, [test0, test1])
        if name == "suite02":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "ciao0"],
                parallelizable=False,
            )

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["0.2", "&&", "echo", "-n", "ciao1"],
                parallelizable=True,
            )

            return Suite(name, [test0, test1])
        elif name == "sleep":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["2"],
                parallelizable=False,
            )

            test1 = Test(
                name="test02",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["2"],
                parallelizable=False,
            )

            return Suite(name, [test0, test1])
        elif name == "environ":
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["-n", "$hello"],
                parallelizable=False,
            )

            return Suite(name, [test0])
        else:
            test0 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="echo",
                args=["Kernel", "panic"],
                parallelizable=False,
            )

            test1 = Test(
                name="test01",
                cwd=self._root,
                env=self._env,
                cmd="sleep",
                args=["0.2"],
                parallelizable=False,
            )

            return Suite(name, [test0, test1])

    async def read_result(
        self, test: Test, stdout: str, retcode: int, exec_t: float
    ) -> TestResults:
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


class _TestSession:
    """
    Test for Session class.
    """

    @pytest.fixture
    async def session(self, tmpdir, sut):
        """
        Session communication object.
        """
        # make sure that ltp folder is present inside the host
        pathlib.Path("/opt/ltp").mkdir(parents=True, exist_ok=True)

        session = Session(tmpdir=TempDir(tmpdir), sut=sut)
        session._framework = DummyFramework()
        yield session
        await asyncio.wait_for(session.stop(), timeout=30)

    async def read_report(self, report):
        report_data = {}
        counter = 0

        while True:
            counter += 1
            try:
                with open(report, "r", encoding="utf-8") as report_file:
                    report_data = json.loads(report_file.read())
                    break
            except FileNotFoundError as ex:
                if counter >= 10:
                    raise ex

                await asyncio.sleep(0.2)

        return report_data

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
            suites=["suite01", "suite02"], pattern="test01|test02", report_path=report
        )

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 4

    async def test_run_report(self, tmpdir, session):
        """
        Test run method when executing suites, generating a report.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite01", "suite02"], report_path=report)

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 4

    async def test_run_stop(self, session):
        """
        Test stop method during run. We are not going to generate any results
        file, because we are not even sure some tests will be executed.
        """

        async def stop():
            await asyncio.sleep(0.2)
            await session.stop()

        await asyncio.gather(
            *[
                session.run(suites=["sleep"]),
                stop(),
            ]
        )

    async def test_run_force_stop(self, session):
        """
        Test stop method when it's called twice. We just ensure that the
        session implementation won't crash or generate exceptions and it will
        forcibly stop the current run.
        """

        async def stop():
            await asyncio.sleep(0.1)
            await session.stop()

        await asyncio.gather(
            *[
                session.run(suites=["sleep"]),
                stop(),
                stop(),
            ]
        )

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

        await asyncio.gather(*[session.run(command="sleep 1"), stop()])

    async def test_run_skip_tests(self, tmpdir, session):
        """
        Test run method when executing suites.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"], skip_tests="test0[23]", report_path=report
        )

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 2

    @pytest.mark.parametrize(
        "iterate,expect",
        [
            (0, 4),
            (1, 4),
            (3, 12),
        ],
    )
    async def test_run_suite_iterate(self, tmpdir, session, iterate, expect):
        """
        Test run method when executing a testing suite multiple times.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"], suite_iterate=iterate, report_path=report
        )

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == expect

    @pytest.mark.xfail(reason="Instable test on CI")
    async def test_run_randomize(self, tmpdir, session):
        """
        Test run method when executing shuffled tests.
        """
        num_of_suites = 10

        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01"] * num_of_suites, randomize=True, report_path=report
        )

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 2 * num_of_suites

        tests_names = []
        for test in report_data["results"]:
            tests_names.append(test["test_fqn"])

        assert ["test01", "test02"] * num_of_suites != tests_names

    @pytest.mark.skip(reason="Instable test on CI")
    async def test_run_runtime(self, tmpdir, session):
        """
        Test run method when executing suites for a certain amount of time.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite01"], runtime=0.5, report_path=report)

        report_data = await self.read_report(report)
        assert len(report_data["results"]) >= 0.5
