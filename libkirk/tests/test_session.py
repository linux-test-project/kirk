"""
Unittests for the session module.
"""

import os
import json
import asyncio
from typing import List

import pytest

import libkirk
from libkirk.ltp import LTPFramework
from libkirk.com import ComChannel, IOBuffer
from libkirk.data import Test, Suite
from libkirk.errors import CommunicationError
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
    async def session(self, tmpdir, sut, monkeypatch):
        """
        Session communication object.
        """
        # Dummy suites only use shell commands; /tmp also exists on remote targets.
        monkeypatch.setenv("LTPROOT", "/tmp")

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
            suites=["suite01", "suite02"], pattern="^test01$", report_path=report
        )

        report_data = await self.read_report(report)
        assert [result["test_fqn"] for result in report_data["results"]] == [
            "test01", "test01"
        ]

    async def test_run_report(self, tmpdir, session):
        """
        Test run method when executing suites, generating a report.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite01", "suite02"], report_path=report)

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 4

    async def test_run_report_abort(self, tmpdir, session):
        """
        Test that results collected before an abort mid-suite are still
        persisted. The scheduler raises after having run and collected the
        results, mimicking a SUT connection loss while scheduling.
        """
        real_schedule = session._scheduler.schedule

        async def aborting_schedule(jobs):
            await real_schedule(jobs)
            raise CommunicationError("SUT connection dropped mid-suite")

        session._scheduler.schedule = aborting_schedule

        report = str(tmpdir / "report.json")
        with pytest.raises(CommunicationError):
            await session.run(suites=["suite01"], report_path=report)

        report_data = await self.read_report(report)
        assert len(report_data["results"]) == 2

    async def test_run_dry_run(self, tmpdir, session, monkeypatch, run_events):
        """
        Test run method with dry_run: no tests are executed and no report
        is generated.
        """
        selected = asyncio.Queue()

        async def report_selection(suites):
            await selected.put([
                (suite.name, [test.name for test in suite.tests]) for suite in suites
            ])

        async def unexpected_schedule(jobs):
            pytest.fail("Dry run must not schedule tests")

        libkirk.events.register("session_dry_run", report_selection)
        monkeypatch.setattr(session._scheduler, "schedule", unexpected_schedule)
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"], pattern="^test01$",
            report_path=report, dry_run=True
        )

        assert await asyncio.wait_for(selected.get(), timeout=5) == [
            ("suite01", ["test01"]), ("suite02", ["test01"])
        ]
        assert not os.path.exists(report)
        assert not os.path.exists(os.path.join(session._tmpdir.abspath, "results.json"))
        assert session._results == []

    @pytest.fixture
    async def running_test(self, session, monkeypatch):
        """Signal when the sleep test is running on the target."""
        started = asyncio.Event()
        channel = session._sut.get_channel()
        run_command = channel.run_command

        async def run(command, cwd=None, env=None, iobuffer=None):
            if command == "sleep 2":
                output = iobuffer

                class StartedBuffer(IOBuffer):
                    async def write(self, data: str) -> None:
                        if output is not None:
                            await output.write(data)
                        started.set()

                iobuffer = StartedBuffer()
                command = "echo ready; sleep 2; echo completed"

            return await run_command(command, cwd=cwd, env=env, iobuffer=iobuffer)

        monkeypatch.setattr(channel, "run_command", run)
        return started

    async def test_run_stop(self, tmpdir, session, running_test):
        """Graceful stop finishes the running test and leaves queued tests unrun."""
        report = str(tmpdir / "report.json")

        async def stop():
            await running_test.wait()
            await session.stop()

        await asyncio.wait_for(
            asyncio.gather(session.run(suites=["sleep"], report_path=report), stop()),
            timeout=30,
        )

        data = await self.read_report(report)
        assert [result["test_fqn"] for result in data["results"]] == ["test01"]
        assert data["results"][0]["test"]["retval"] == ["0"]
        assert data["results"][0]["test"]["log"] == "ready\ncompleted\n"
        assert not await session._sut.is_running()

    async def test_run_force_stop(self, tmpdir, session, running_test):
        """A second stop kills the running test and leaves queued tests unrun."""
        report = str(tmpdir / "report.json")

        async def stop():
            await running_test.wait()
            await asyncio.gather(session.stop(), session.stop())

        await asyncio.wait_for(
            asyncio.gather(session.run(suites=["sleep"], report_path=report), stop()),
            timeout=30,
        )

        data = await self.read_report(report)
        # Channels may omit the killed test or report its interrupted result.
        assert len(data["results"]) <= 1
        for result in data["results"]:
            assert result["test_fqn"] == "test01"
            assert result["test"]["retval"] != ["0"]
            assert "completed" not in result["test"]["log"]
        assert not await session._sut.is_running()

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

    @pytest.mark.parametrize("randomize", [False, True])
    async def test_run_randomize(self, tmpdir, session, monkeypatch, randomize):
        """
        Test run method when executing shuffled tests.
        """
        monkeypatch.setattr("libkirk.session.random.shuffle", lambda tests: tests.reverse())

        report = str(tmpdir / "report.json")
        await asyncio.wait_for(
            session.run(
                suites=["suite01"],
                randomize=randomize,
                report_path=report,
            ),
            timeout=30,
        )

        report_data = await self.read_report(report)
        expected = ["test02", "test01"] if randomize else ["test01", "test02"]
        assert [result["test_fqn"] for result in report_data["results"]] == expected

    @pytest.mark.skip(reason="Instable test on CI")
    async def test_run_runtime(self, tmpdir, session):
        """
        Test run method when executing suites for a certain amount of time.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite01"], runtime=0.5, report_path=report)

        report_data = await self.read_report(report)
        assert len(report_data["results"]) >= 0.5

    def test_apply_sharding(self):
        """
        Test Session._apply_sharding round-robin algorithm.
        """
        tests = [Test(name=f"test{i}", cmd="echo") for i in range(10)]

        s1 = [Suite("mysuite", list(tests))]
        Session._apply_sharding(s1, (1, 3))
        assert [t.name for t in s1[0].tests] == ["test0", "test3", "test6", "test9"]

        s2 = [Suite("mysuite", list(tests))]
        Session._apply_sharding(s2, (2, 3))
        assert [t.name for t in s2[0].tests] == ["test1", "test4", "test7"]

        s3 = [Suite("mysuite", list(tests))]
        Session._apply_sharding(s3, (3, 3))
        assert [t.name for t in s3[0].tests] == ["test2", "test5", "test8"]

        # None shard should not modify tests
        s_none = [Suite("mysuite", list(tests))]
        Session._apply_sharding(s_none, None)
        assert len(s_none[0].tests) == 10

    @pytest.mark.parametrize(
        "shard,expected_test",
        [
            ((1, 2), "test01"),
            ((2, 2), "test02"),
        ],
    )
    async def test_run_shard(self, tmpdir, session, shard, expected_test):
        """
        Test run method with sharding.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite01"], shard=shard, report_path=report)
        data = await self.read_report(report)
        assert len(data["results"]) == 1
        assert data["results"][0]["test_fqn"] == expected_test

    async def test_run_shard_multiple_suites(self, tmpdir, session):
        """
        Test sharding across multiple suites with empty suite pruning.
        """
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01", "suite02"], shard=(1, 2), report_path=report
        )
        data = await self.read_report(report)
        assert len(data["results"]) == 2

    async def test_run_shard_with_restore(self, tmpdir, session):
        """
        Test that sharding happens before restore so test partitioning remains stable.
        """
        # Simulate previous execution where suite01::test01 was already executed
        executed_file = tmpdir / "executed"
        executed_file.write("suite01::test01\n")

        # Shard (1, 2) should pick test01 (and test03, etc.).
        # Since test01 is already in executed, shard (1, 2) has nothing left in suite01.
        # But shard (2, 2) which owns test02 should still run test02 and not be shifted.
        report = str(tmpdir / "report.json")
        await session.run(
            suites=["suite01"],
            shard=(2, 2),
            restore_path=str(tmpdir),
            report_path=report,
        )
        data = await self.read_report(report)
        assert len(data["results"]) == 1
        assert data["results"][0]["test_fqn"] == "test02"
