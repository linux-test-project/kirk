"""
Unittests for runner module.
"""

from libkirk.ltp import LTPFramework
import asyncio
import os
from types import SimpleNamespace

import pytest

import libkirk
from typing import Optional

from libkirk.data import Suite, Test
from libkirk.framework import Framework
from libkirk.results import ResultStatus, TestResults
from libkirk.errors import KernelPanicError, KernelTaintedError, KernelTimeoutError
from libkirk.sut import SUT
from libkirk.sut_base import GenericSUT
from libkirk.scheduler import SuiteScheduler, TestScheduler


class MockSUT(GenericSUT):
    """
    GenericSUT mock.
    """

    async def get_info(self) -> dict:
        return {
            "distro": "openSUSE",
            "distro_ver": "15.3",
            "kernel": "5.10",
            "cmdline": "ima_policy=tcb",
            "arch": "x86_64",
            "cpu": "x86_64",
            "swap": "0",
            "ram": "1M",
        }

    async def get_tainted_info(self) -> tuple:
        return 0, [""]


class MockTestScheduler(TestScheduler):
    """
    TestScheduler mock that is not checking for tainted kernel
    and it doesn't write into /dev/kmsg
    """

    async def _write_kmsg(
        self, test: Test, results: Optional[TestResults] = None
    ) -> None:
        pass


class MockSuiteScheduler(SuiteScheduler):
    """
    SuiteScheduler mock that traces SUT reboots.
    """

    def __init__(
        self,
        sut: SUT,
        framework: Framework,
        suite_timeout: float = 0.0,
        exec_timeout: float = 0.0,
        max_workers: int = 1,
    ) -> None:
        super().__init__(
            sut=sut,
            framework=framework,
            suite_timeout=suite_timeout,
            exec_timeout=exec_timeout,
            max_workers=max_workers,
        )
        self._scheduler = MockTestScheduler(
            sut=self._sut,
            framework=self._framework,
            timeout=exec_timeout,
            max_workers=max_workers,
        )
        self._rebooted = 0

    async def _restart_sut(self) -> None:
        self._logger.info("Rebooting the SUT")

        await self._scheduler.stop()
        await self._sut.restart()

        self._rebooted += 1

    @property
    def rebooted(self) -> int:
        return self._rebooted


@pytest.fixture
async def sut():
    """
    SUT object.
    """
    obj = MockSUT()
    obj.setup(com="shell")
    await obj.start()
    yield obj

    if await obj.is_running():
        await obj.stop()


@pytest.fixture
async def commands(sut, monkeypatch, workers):
    """
    Hold test commands until released and record completion or cancellation.
    """
    state = SimpleNamespace(
        started=asyncio.Event(), release=asyncio.Event(),
        running=set(), completed=[], cancelled=[],
    )

    async def run_command(command, cwd=None, env=None, iobuffer=None):
        # Test timeout handling pings the channel to check that the SUT is alive.
        if command == "test .":
            return {"returncode": 0, "stdout": "", "exec_time": 0.01}

        state.running.add(command)
        if len(state.running) == workers:
            state.started.set()
        try:
            await state.release.wait()
            state.completed.append(command)
            return {"returncode": 0, "stdout": "", "exec_time": 0.01}
        except asyncio.CancelledError:
            state.cancelled.append(command)
            raise
        finally:
            state.running.remove(command)

    monkeypatch.setattr(sut.get_channel(), "run_command", run_command)
    return state


class TestTestScheduler:
    """
    Tests for TestScheduler.
    """

    @pytest.fixture
    async def create_runner(self, sut, ltpdir):
        def _callback(timeout: float = 3600.0, max_workers: int = 1) -> TestScheduler:
            obj = MockTestScheduler(
                sut=sut,
                framework=LTPFramework(),
                timeout=timeout,
                max_workers=max_workers,
            )

            return obj

        yield _callback

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule(self, workers, create_runner):
        """
        Test the schedule method.
        """
        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["-n", "ciao"],
                    parallelizable=True,
                )
            )

        runner = create_runner(max_workers=workers)

        await runner.schedule(tests)
        assert len(runner.results) == len(tests)

        sorted_results = sorted(runner.results, key=lambda res: res.test.name)

        index = 0
        for res in sorted_results:
            assert res.test.name == f"test{index}"
            assert res.passed == 1
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 0
            assert res.warnings == 0
            assert res.exec_time > 0
            assert res.return_code == 0
            assert res.stdout == "ciao"
            index += 1

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_stop(self, workers, create_runner, commands):
        """
        Test the schedule method when stop is called.
        """
        num_tests = workers * 2

        tests = []
        for i in range(num_tests):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd=f"test{i}",
                    parallelizable=True,
                )
            )

        runner = create_runner(max_workers=workers)

        async def stop():
            await commands.started.wait()
            # stop() sets its stop flag before yielding to the release callback.
            libkirk.get_event_loop().call_soon(commands.release.set)
            await runner.stop()

        await asyncio.wait_for(asyncio.gather(runner.schedule(tests), stop()), timeout=5)

        expected = [f"test{i}" for i in range(workers)]
        assert sorted(res.test.name for res in runner.results) == expected
        assert sorted(commands.completed) == expected
        assert not commands.running
        assert not commands.cancelled
        assert runner.stopped

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_tainted(self, workers, create_runner):
        """
        Test the schedule method when kernel is tainted.
        """
        tainted = []

        async def mock_tainted():
            if tainted:
                return 1, ["proprietary module was loaded"]

            # switch to tainted status _after_ test
            tainted.append(1)
            return 0, [""]

        runner = create_runner(max_workers=workers)
        runner._get_tainted_status = mock_tainted

        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["-n", "ciao"],
                    parallelizable=True,
                )
            )

        with pytest.raises(KernelTaintedError):
            await runner.schedule(tests)

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_panic(self, workers, sut, create_runner, monkeypatch):
        """
        Test the schedule method on kernel panic.
        """
        channel = sut.get_channel()
        run_command = channel.run_command
        started = asyncio.Event()
        blocked = asyncio.Event()
        running = set()

        async def panic_command(command, cwd=None, env=None, iobuffer=None):
            if command.startswith("echo"):
                if workers > 1:
                    await started.wait()
                return await run_command(command, cwd=cwd, env=env, iobuffer=iobuffer)

            running.add(command)
            if len(running) == workers - 1:
                started.set()
            try:
                await blocked.wait()
            finally:
                running.remove(command)

        monkeypatch.setattr(channel, "run_command", panic_command)

        tests = []
        tests.append(
            Test(
                name="test0",
                cmd="echo",
                args=["Kernel", "panic"],
                parallelizable=True,
            )
        )

        for i in range(1, 10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="sleep",
                    args=[str(i)],
                    parallelizable=True,
                )
            )

        runner = create_runner(max_workers=workers)

        with pytest.raises(KernelPanicError):
            await asyncio.wait_for(runner.schedule(tests), timeout=5)

        assert not running
        assert len(runner.results) == 1

        res = runner.results[0]
        assert res.test.name == "test0"
        assert res.passed == 0
        assert res.failed == 0
        assert res.broken == 1
        assert res.skipped == 0
        assert res.warnings == 0
        assert res.exec_time > 0
        assert res.return_code == -1
        assert res.stdout == "Kernel panic\n"

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_timeout(self, workers, sut, create_runner):
        """
        Test the schedule method on kernel timeout.
        """
        async def kernel_timeout(command, cwd=None, env=None, iobuffer=None) -> dict:
            raise asyncio.TimeoutError()

        sut.get_channel().run_command = kernel_timeout
        runner = create_runner(max_workers=workers)

        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="sleep",
                    args=["0.1", "&&", "echo", "-n", "ciao"],
                    parallelizable=True,
                )
            )

        with pytest.raises(KernelTimeoutError):
            await runner.schedule(tests)

    @pytest.mark.parametrize(
        "error", [KernelPanicError, KernelTimeoutError, RuntimeError, asyncio.CancelledError]
    )
    async def test_schedule_error_cleanup(self, create_runner, monkeypatch, error):
        """
        Wait for sibling cancellation cleanup before propagating an error.
        """
        runner = create_runner(max_workers=2)
        started = asyncio.Event()
        blocked = asyncio.Event()
        cleaned = asyncio.Event()

        async def run_test(test):
            if test.name == "error":
                await started.wait()
                raise error()

            started.set()
            try:
                await blocked.wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()

        monkeypatch.setattr(runner, "_run_test", run_test)
        tests = [
            Test(name=name, cmd="echo", parallelizable=True)
            for name in ("error", "sibling")
        ]
        with pytest.raises(error):
            await asyncio.wait_for(runner.schedule(tests), timeout=5)

        assert cleaned.is_set()

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_test_timeout(self, workers, create_runner, commands):
        """
        Test the schedule method on test timeout.
        """
        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd=f"test{i}",
                    parallelizable=True,
                )
            )

        runner = create_runner(timeout=0.05, max_workers=workers)

        await asyncio.wait_for(runner.schedule(tests), timeout=30)
        assert sorted(res.test.name for res in runner.results) == [
            test.name for test in tests
        ]
        assert sorted(commands.cancelled) == [test.name for test in tests]
        assert not commands.running
        assert not commands.completed

        for res in runner.results:
            assert res.passed == 0
            assert res.failed == 0
            assert res.broken == 1
            assert res.skipped == 0
            assert res.warnings == 0
            assert res.exec_time > 0
            assert res.return_code == -1
            assert res.stdout == ""

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_reboot_unsupported(self, workers, create_runner):
        """
        Test that reboot tests on an unsupported SUT channel are skipped with CONF.
        """
        test = Test(name="reboot01", cmd="echo", reboots_sut=True)
        runner = create_runner(max_workers=workers)

        await runner.schedule([test])
        assert len(runner.results) == 1
        res = runner.results[0]
        assert isinstance(res, TestResults)
        assert res.status == ResultStatus.CONF
        assert res.skipped == 1
        assert res.passed == 0
        assert res.failed == 0
        assert res.return_code == 32
        assert "does not support reboot" in res.stdout

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_reboot_success(self, workers):
        """
        Test two-phase execution of a reboot test on a supported SUT.
        """
        commands_run = []
        restarted = []

        class MockRebootSUT(MockSUT):
            @property
            def supports_reboot(self) -> bool:
                return True

            async def restart(self, iobuffer=None, retries=150, delay=2.0) -> None:
                restarted.append(True)

        sut = MockRebootSUT()
        sut.setup(com="shell")
        await sut.start()

        orig_run_command = sut.get_channel().run_command

        # pyrefly: ignore[bad-assignment]
        async def mock_run_cmd(command, cwd=None, env=None, iobuffer=None):
            commands_run.append(command)
            if "-P 1" in command:
                return {
                    "command": command,
                    "returncode": 0,
                    "stdout": "reboot01 1 TINFO: rebooting\n",
                    "exec_time": 0.05,
                }
            elif "-P 2" in command:
                return {
                    "command": command,
                    "returncode": 0,
                    "stdout": "reboot01 1 TPASS: rebooted successfully\n",
                    "exec_time": 0.05,
                }
            return await orig_run_command(command, cwd=cwd, env=env, iobuffer=iobuffer)

        sut.get_channel().run_command = mock_run_cmd

        runner = MockTestScheduler(
            sut=sut,
            framework=LTPFramework(),
            timeout=3600.0,
            max_workers=workers,
        )

        test = Test(name="reboot01", cmd="reboot01", reboots_sut=True)
        await runner.schedule([test])

        assert len(runner.results) == 1
        res = runner.results[0]
        assert isinstance(res, TestResults)
        assert res.passed == 1
        assert res.failed == 0
        assert res.status == ResultStatus.PASS
        assert len(restarted) == 1
        assert any("-P 1" in c for c in commands_run)
        assert any("-P 2" in c for c in commands_run)

        await sut.stop()

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_reboot_phase1_failure(self, workers):
        """
        Test that reboot test failing in phase 1 does not restart SUT or run phase 2.
        """
        commands_run = []
        restarted = []

        class MockRebootSUT(MockSUT):
            @property
            def supports_reboot(self) -> bool:
                return True

            async def restart(self, iobuffer=None, retries=150, delay=2.0) -> None:
                restarted.append(True)

        sut = MockRebootSUT()
        sut.setup(com="shell")
        await sut.start()

        # pyrefly: ignore[bad-assignment]
        async def mock_run_cmd(command, cwd=None, env=None, iobuffer=None):
            commands_run.append(command)
            if "-P 1" in command:
                return {
                    "command": command,
                    "returncode": 1,
                    "stdout": "reboot01 1 TFAIL: setup failed\n",
                    "exec_time": 0.05,
                }
            return {"command": command, "returncode": 0, "stdout": "", "exec_time": 0.05}

        sut.get_channel().run_command = mock_run_cmd

        runner = MockTestScheduler(
            sut=sut,
            framework=LTPFramework(),
            timeout=3600.0,
            max_workers=workers,
        )

        test = Test(name="reboot01", cmd="reboot01", reboots_sut=True)
        await runner.schedule([test])

        assert len(runner.results) == 1
        res = runner.results[0]
        assert isinstance(res, TestResults)
        assert res.failed == 1
        assert res.passed == 0
        assert len(restarted) == 0
        assert not any("-P 2" in c for c in commands_run)

        await sut.stop()

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_reboot_reconnect_failure(self, workers):
        """
        Test that a failure to reconnect to SUT after reboot raises KernelTimeoutError.
        """
        from libkirk.errors import CommunicationError

        class MockRebootSUT(MockSUT):
            @property
            def supports_reboot(self) -> bool:
                return True

            async def restart(self, iobuffer=None, retries=150, delay=2.0) -> None:
                raise CommunicationError("SUT unreachable")

        sut = MockRebootSUT()
        sut.setup(com="shell")
        await sut.start()

        # pyrefly: ignore[bad-assignment]
        async def mock_run_cmd(command, cwd=None, env=None, iobuffer=None):
            return {"command": command, "returncode": 0, "stdout": "", "exec_time": 0.05}

        sut.get_channel().run_command = mock_run_cmd

        runner = MockTestScheduler(
            sut=sut,
            framework=LTPFramework(),
            timeout=3600.0,
            max_workers=workers,
        )

        test = Test(name="reboot01", cmd="reboot01", reboots_sut=True)
        with pytest.raises(KernelTimeoutError):
            await runner.schedule([test])

        assert len(runner.results) == 1
        res = runner.results[0]
        assert isinstance(res, TestResults)
        assert res.failed == 1
        assert "Failed to reconnect to SUT after reboot" in res.stdout

        await sut.stop()


class TestSuiteScheduler:
    """
    Tests for SuiteScheduler.
    """

    @pytest.fixture
    async def create_runner(self, sut, ltpdir):
        def _callback(
            suite_timeout: float = 3600.0,
            exec_timeout: float = 3600.0,
            max_workers: int = 1,
        ) -> SuiteScheduler:
            obj = MockSuiteScheduler(
                sut=sut,
                framework=LTPFramework(),
                suite_timeout=suite_timeout,
                exec_timeout=exec_timeout,
                max_workers=max_workers,
            )

            return obj

        yield _callback

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule(self, workers, create_runner):
        """
        Test the schedule method.
        """
        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["-n", "ciao"],
                    parallelizable=True,
                )
            )

        runner = create_runner(max_workers=workers)
        await runner.schedule([Suite("suite01", tests)])

        assert len(runner.results) == 1
        assert len(runner.results[0].tests_results) == 10

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_stop(self, workers, create_runner, commands):
        """
        Test the schedule method when stop is called.
        """
        num_tests = workers * 2
        tests = []
        for i in range(num_tests):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd=f"test{i}",
                    parallelizable=True,
                )
            )
        runner = create_runner(max_workers=workers)

        async def stop():
            await commands.started.wait()
            # stop() sets its stop flag before yielding to the release callback.
            libkirk.get_event_loop().call_soon(commands.release.set)
            await runner.stop()

        await asyncio.wait_for(
            asyncio.gather(runner.schedule([Suite("suite01", tests)]), stop()),
            timeout=5,
        )

        assert len(runner.results) == 1
        expected = [f"test{i}" for i in range(workers)]
        assert sorted(res.test.name for res in runner.results[0].tests_results) == expected
        assert sorted(commands.completed) == expected
        assert not commands.running
        assert not commands.cancelled
        assert runner.stopped

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_tainted(self, workers, sut, create_runner):
        """
        Test the schedule method when kernel is tainted.
        """
        tainted = []
        index = 0
        value = 0

        for msg in sut.TAINTED_MSG:
            tainted.append((value, [msg]))
            value = pow(2, index)
            index += 1

        async def mock_tainted():
            return tainted.pop()

        sut.get_tainted_info = mock_tainted
        runner = create_runner(max_workers=workers)

        tests = []
        for i in range(2):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["-n", "ciao"],
                    parallelizable=True,
                )
            )
        await runner.schedule([Suite("suite01", tests)])

        if workers > 1:
            assert runner.rebooted >= 1
        else:
            assert runner.rebooted == 2

        assert len(runner.results) == 1
        assert sorted(res.test.name for res in runner.results[0].tests_results) == [
            test.name for test in tests
        ]

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_panic(self, workers, create_runner):
        """
        Test the schedule method on kernel panic.
        """
        runner = create_runner(max_workers=workers)

        tests = []
        for i in range(0, 9):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["-n", "ciao"],
                    parallelizable=True,
                )
            )
        tests.append(
            Test(
                name="test9",
                cmd="echo",
                args=["-n", "Kernel", "panic"],
                parallelizable=True,
            )
        )
        await runner.schedule([Suite("suite01", tests)])

        assert runner.rebooted == 1
        assert len(runner.results) == 1
        assert sorted(res.test.name for res in runner.results[0].tests_results) == [
            test.name for test in tests
        ]

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_kernel_timeout(self, workers, sut, create_runner):
        """
        Test the schedule method on kernel timeout.
        """

        async def kernel_timeout(command, cwd=None, env=None, iobuffer=None) -> dict:
            raise asyncio.TimeoutError()

        sut.get_channel().run_command = kernel_timeout
        runner = create_runner(max_workers=workers)

        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd="echo",
                    args=["ciao"],
                    parallelizable=True,
                )
            )
        await runner.schedule([Suite("suite01", tests)])

        assert runner.rebooted > 0
        assert len(runner.results) == 1
        assert len(runner.results[0].tests_results) == len(tests)

    @pytest.mark.parametrize("workers", [1, 10])
    async def test_schedule_suite_timeout(self, workers, create_runner, commands):
        """
        Test the schedule method on suite timeout.
        """
        runner = create_runner(suite_timeout=0.1, max_workers=workers)

        tests = []
        for i in range(10):
            tests.append(
                Test(
                    name=f"test{i}",
                    cmd=f"test{i}",
                    parallelizable=True,
                )
            )
        await asyncio.wait_for(runner.schedule([Suite("suite01", tests)]), timeout=30)

        assert runner.results[0].exec_time == 0.0
        assert len(runner.results[0].tests_results) == len(tests)
        assert commands.started.is_set()
        assert sorted(commands.cancelled) == [f"test{i}" for i in range(workers)]
        assert not commands.running
        assert not commands.completed

        for i in range(len(tests)):
            res = runner.results[0].tests_results[i]
            assert res.test.name == f"test{i}"
            assert res.passed == 0
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 1
            assert res.warnings == 0
            assert res.exec_time == 0
            assert res.return_code == 32
            assert res.stdout == ""
            assert res.status == ResultStatus.CONF
