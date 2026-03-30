"""
Unittests for ui module.
"""

import asyncio

import pytest

import libkirk
from libkirk.data import Suite, Test
from libkirk.results import SuiteResults, TestResults
from libkirk.ui import (
    ConsoleUserInterface,
    ParallelUserInterface,
    SimpleUserInterface,
    VerboseUserInterface,
)


class TestUserFriendlyDuration:
    """
    Test _user_friendly_duration static method.
    """

    def test_zero(self):
        assert ConsoleUserInterface._user_friendly_duration(0) == "0h 0m 0s"

    def test_seconds_only(self):
        result = ConsoleUserInterface._user_friendly_duration(5.123)
        assert result == "5.123s"

    def test_minutes_and_seconds(self):
        result = ConsoleUserInterface._user_friendly_duration(125)
        assert result == "2m 5s"

    def test_hours_minutes_seconds(self):
        result = ConsoleUserInterface._user_friendly_duration(3661)
        assert result == "1h 1m 1s"


class TestFormatCmdline:
    """
    Test _format_cmdline static method.
    """

    def test_none(self):
        assert ConsoleUserInterface._format_cmdline(None) == ""

    def test_empty(self):
        assert ConsoleUserInterface._format_cmdline("") == ""

    def test_single_param(self):
        assert ConsoleUserInterface._format_cmdline("root=/dev/sda") == "root=/dev/sda"

    def test_multiple_params(self):
        result = ConsoleUserInterface._format_cmdline("root=/dev/sda console=ttyS0")
        assert "root=/dev/sda" in result
        assert "console=ttyS0" in result


class TestResultColor:
    """
    Test _result_color method.
    """

    @pytest.fixture
    def ui(self):
        ui = ConsoleUserInterface.__new__(ConsoleUserInterface)
        ui._no_colors = False
        return ui

    def _make_results(self, passed=0, failed=0, skipped=0, broken=0, warnings=0):
        test = Test(name="t", cmd="echo")
        return TestResults(
            test=test,
            passed=passed,
            failed=failed,
            broken=broken,
            skipped=skipped,
            warnings=warnings,
            exec_time=0.1,
            retcode=0,
            stdout="",
        )

    def test_pass(self, ui):
        result = self._make_results(passed=1)
        msg, color = ui._result_color(result)
        assert msg == "pass"
        assert color == ConsoleUserInterface.GREEN

    def test_fail(self, ui):
        result = self._make_results(failed=1)
        msg, color = ui._result_color(result)
        assert msg == "fail"
        assert color == ConsoleUserInterface.RED

    def test_skip(self, ui):
        result = self._make_results(skipped=1)
        msg, color = ui._result_color(result)
        assert msg == "skip"
        assert color == ConsoleUserInterface.CYAN

    def test_broken(self, ui):
        result = self._make_results(broken=1)
        msg, color = ui._result_color(result)
        assert msg == "broken"
        assert color == ConsoleUserInterface.RED


class TestSimpleUserInterface:
    """
    Test SimpleUserInterface event handlers.
    """

    @pytest.fixture
    def ui(self):
        return SimpleUserInterface(no_colors=True)

    def _make_test(self, name="t1"):
        return Test(name=name, cmd="echo")

    def _make_results(self, test=None, passed=0, failed=0, broken=0,
                      skipped=0, warnings=0):
        if test is None:
            test = self._make_test()
        return TestResults(
            test=test,
            passed=passed,
            failed=failed,
            broken=broken,
            skipped=skipped,
            warnings=warnings,
            exec_time=0.1,
            retcode=0,
            stdout="",
        )

    async def test_sut_not_responding(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        await ui.sut_not_responding()

        # test_completed should skip printing result
        results = self._make_results(passed=1)
        await ui.test_completed(results)

        await asyncio.sleep(0.05)
        await libkirk.events.stop()

        out, _ = capsys.readouterr()
        assert "SUT not responding" in out

    async def test_kernel_panic(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        await ui.kernel_panic()

        results = self._make_results(passed=1)
        await ui.test_completed(results)

        await asyncio.sleep(0.05)
        await libkirk.events.stop()

        out, _ = capsys.readouterr()
        assert "kernel panic" in out

    async def test_kernel_tainted(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        await ui.kernel_tainted("proprietary module")
        results = self._make_results(passed=1)
        await ui.test_completed(results)

        while "tainted" not in capsys.readouterr().out:
            await asyncio.sleep(1e-3)

        await libkirk.events.stop()

    async def test_test_timed_out(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        test = self._make_test()
        await ui.test_timed_out(test, 30)

        results = self._make_results(passed=1)
        await ui.test_completed(results)

        await asyncio.sleep(0.05)
        await libkirk.events.stop()

        out, _ = capsys.readouterr()
        assert "timed out" in out


class TestVerboseUserInterface:
    """
    Test VerboseUserInterface event handlers.
    """

    @pytest.fixture
    def ui(self):
        return VerboseUserInterface(no_colors=True)

    async def test_sut_stdout(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        await ui.sut_stdout("mysut", "hello from sut")

        while "hello from sut" not in capsys.readouterr().out:
            await asyncio.sleep(1e-3)

        await libkirk.events.stop()

    async def test_kernel_tainted(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        await ui.kernel_tainted("proprietary module")

        while "Tainted kernel" not in capsys.readouterr().out:
            await asyncio.sleep(1e-3)

        await libkirk.events.stop()

    async def test_test_timed_out(self, ui, capsys):
        async def start():
            await libkirk.events.start()

        libkirk.create_task(start())

        test = Test(name="t1", cmd="echo")
        await ui.test_timed_out(test, 30)

        results = TestResults(
            test=test,
            passed=0,
            failed=0,
            broken=0,
            skipped=0,
            warnings=0,
            exec_time=0.1,
            retcode=0,
            stdout="",
        )
        await ui.test_completed(results)

        while "timed out" not in capsys.readouterr().out:
            await asyncio.sleep(1e-3)

        await libkirk.events.stop()
