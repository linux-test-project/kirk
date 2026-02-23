"""
.. module:: ui
    :platform: Linux
    :synopsis: module that contains user interface

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import platform
import sys
import traceback
from typing import (
    List,
    Optional,
)

import libkirk
from libkirk.data import (
    Suite,
    Test,
)
from libkirk.results import (
    SuiteResults,
    TestResults,
)


class ConsoleUserInterface:
    """
    Console based user interface.
    """

    WHITE = "\033[1;37m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    CYAN = "\033[1;36m"
    RESET_COLOR = "\033[0m"
    RESET_SCREEN = "\033[2J"

    def __init__(self, no_colors: bool = False) -> None:
        self._no_colors = no_colors
        self._line = ""
        self._restore = ""
        self._num_suites = 1

        event_handlers = {
            "session_restore": self.session_restore,
            "session_started": self.session_started,
            "session_stopped": self.session_stopped,
            "sut_start": self.sut_start,
            "sut_stop": self.sut_stop,
            "sut_restart": self.sut_restart,
            "run_cmd_start": self.run_cmd_start,
            "run_cmd_stdout": self.run_cmd_stdout,
            "run_cmd_stop": self.run_cmd_stop,
            "suite_started": self.suite_started,
            "suite_completed": self.suite_completed,
            "suite_timeout": self.suite_timeout,
            "session_warning": self.session_warning,
            "session_error": self.session_error,
            "session_completed": self.session_completed,
            "internal_error": self.internal_error,
        }

        for event_name, handler in event_handlers.items():
            libkirk.events.register(event_name, handler)

        # we register a special event 'printf' with ordered coroutines,
        # so we ensure that print threads will be executed one after the
        # other and user interface will be printed in the correct way
        libkirk.events.register("printf", self.print_message, ordered=True)

    async def _print(
        self, msg: str, color: Optional[str] = None, end: str = "\n"
    ) -> None:
        """
        Fire a `printf` event.
        """
        msg = msg.replace(self.RESET_SCREEN, "").replace("\r", "")

        if color and not self._no_colors:
            msg = f"{color}{msg}{self.RESET_COLOR}"

        await libkirk.events.fire("printf", msg, end=end, flush=True)

    async def print_message(
        self, msg: str, end: str = "\n", flush: bool = True
    ) -> None:
        """
        Print a message in console, avoiding any I/O blocking operation
        done by the `print` built-in function, using `asyncio.to_thread()`.
        """

        def _wrap() -> None:
            print(msg, end=end, flush=flush)

        await libkirk.to_thread(_wrap)

    @staticmethod
    def _user_friendly_duration(duration: float) -> str:
        """
        Return a user-friendly duration time from seconds.
        For example, "3670.234" becomes "1h 0m 10s".
        """
        if duration == 0:
            return "0h 0m 0s"

        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"
        elif minutes > 0:
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            return f"{seconds:.3f}s"

    @staticmethod
    def _format_cmdline(cmdline: Optional[str]) -> str:
        """
        Format cmdline to show kernel parameters on multiple lines
        while preserving initial spaces.
        """
        if not cmdline:
            return ""

        parts = cmdline.split()
        if not parts:
            return cmdline

        formatted = parts[0]
        for part in parts[1:]:
            formatted += f"\n          {part}"

        return formatted

    def _result_color(self, results: TestResults) -> tuple:
        """
        Return test result string and the color associated to it.
        """
        if results.failed > 0:
            return "fail", self.RED
        if results.skipped > 0:
            return "skip", self.CYAN
        if results.broken > 0:
            return "broken", self.RED

        return "pass", self.GREEN

    async def _print_underline(self, msg: str) -> None:
        """
        Print an underlined message.
        """
        final_msg = f"{msg}\n{'─' * len(msg)}"
        await self._print(final_msg)

    async def _print_section(self, msg: str) -> None:
        """
        Print a section title surrounded by lines.
        """
        line = "─" * (len(msg) + 12)
        space = " " * 6
        await self._print(f"{line}\n{space}{msg}\n{line}")

    async def _print_target_info(self, results: SuiteResults) -> None:
        """
        Print target information.
        """
        message = (
            f"Kernel:   {results.kernel}\n"
            f"Cmdline:  {self._format_cmdline(results.cmdline)}\n"
            f"Machine:  {results.cpu}\n"
            f"Arch:     {results.arch}\n"
            f"RAM:      {results.ram}\n"
            f"Swap:     {results.swap}\n"
            f"Distro:   {results.distro} {results.distro_ver}\n"
        )

        await self._print_underline("Target information")
        await self._print(message)

    async def _print_summary(self, results: List[SuiteResults]) -> None:
        """
        Print a summary for a list of testing suites.
        """
        suites = ", ".join([s_res.suite.name for s_res in results])
        test_runs = sum(len(res.tests_results) for res in results)
        passed = sum(result.passed for result in results)
        failed = sum(result.failed for result in results)
        skipped = sum(result.skipped for result in results)
        broken = sum(result.broken for result in results)
        warnings = sum(result.warnings for result in results)
        exec_time = sum(result.exec_time for result in results)
        exec_time_uf = self._user_friendly_duration(exec_time)

        message = (
            f"Suite:   {suites}\n"
            f"Runtime: {exec_time_uf}\n"
            f"Runs:    {test_runs}\n\n"
            "Results:\n"
            f"    Passed:   {passed}\n"
            f"    Failed:   {failed}\n"
            f"    Broken:   {broken}\n"
            f"    Skipped:  {skipped}\n"
            f"    Warnings: {warnings}\n"
        )
        await self._print(message)

    async def session_restore(self, restore: str) -> None:
        await self._print(f"Restore session: {restore}")

    async def session_started(self, suites: list, tmpdir: str) -> None:
        self._num_suites = len(suites) if suites is not None else 0

        uname = platform.uname()
        message = (
            "Host information\n"
            f"\tHostname:   {uname.node}\n"
            f"\tPython:     {sys.version}\n"
            f"\tDirectory:  {tmpdir}\n"
        )

        await self._print(message)

    async def session_stopped(self) -> None:
        await self._print("Session stopped")

    async def sut_start(self, sut: str) -> None:
        await self._print(f"Connecting to SUT: {sut}\n")

    async def sut_stop(self, sut: str) -> None:
        await self._print(f"Disconnecting from SUT: {sut}")

    async def sut_restart(self, sut: str) -> None:
        await self._print(f"Restarting SUT: {sut}")

    async def run_cmd_start(self, cmd: str) -> None:
        await self._print(f"{cmd}", color=self.CYAN)

    async def run_cmd_stdout(self, data: str) -> None:
        await self._print(data, end="")

    async def run_cmd_stop(self, command: str, stdout: str, returncode: int) -> None:
        await self._print(f"\nExit code: {returncode}\n")

    async def suite_started(self, suite: Suite) -> None:
        suite_msg = f"Suite: {suite.name}"
        await self._print_underline(suite_msg)

    async def suite_completed(self, results: SuiteResults, exec_time: float) -> None:
        exec_time_uf = self._user_friendly_duration(exec_time)

        message = f"\nExecution time: {exec_time_uf}\n"

        await self._print(message)

        # there's no need to print more than one summary if we only have
        # one testing suite
        if self._num_suites > 1:
            await self._print_summary([results])

    async def suite_timeout(self, suite: Suite, timeout: float) -> None:
        await self._print(
            f"Suite '{suite.name}' timed out after {timeout} seconds", color=self.RED
        )

    async def session_warning(self, msg: str) -> None:
        await self._print(f"Warning: {msg}", color=self.YELLOW)

    async def session_error(self, error: str) -> None:
        await self._print(f"Error: {error}", color=self.RED)

    async def session_completed(self, results: List[SuiteResults]) -> None:
        if not results:
            return

        await self._print("")
        await self._print_target_info(results[0])
        await self._print_section("TEST SUMMARY")
        await self._print_summary(results)

        t_broken = []
        t_failed = []

        for s_res in results:
            for t_res in s_res.tests_results:
                if t_res.failed > 0:
                    t_failed.append(t_res)
                if t_res.broken > 0:
                    t_broken.append(t_res)

        if t_broken:
            await self._print("Broken:", color=self.RED)
            msg = [f"    • {t.test.name}" for t in t_broken]
            await self._print("\n".join(msg))
            await self._print("")

        if t_failed:
            await self._print("Failures:", color=self.RED)
            msg = [f"    • {t.test.name}" for t in t_failed]
            await self._print("\n".join(msg))
            await self._print("")

    async def internal_error(self, exc: BaseException, func_name: str) -> None:
        await self._print(
            f"\nUI error in function '{func_name}': {exc}\n", color=self.RED
        )

        traceback.print_exc()


class SimpleUserInterface(ConsoleUserInterface):
    """
    Console based user interface without many fancy stuff.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted: Optional[str] = None
        self._timed_out = False

        libkirk.events.register("sut_not_responding", self.sut_not_responding)
        libkirk.events.register("kernel_panic", self.kernel_panic)
        libkirk.events.register("kernel_tainted", self.kernel_tainted)
        libkirk.events.register("test_timed_out", self.test_timed_out)
        libkirk.events.register("test_started", self.test_started)
        libkirk.events.register("test_completed", self.test_completed)

    async def sut_not_responding(self) -> None:
        self._sut_not_responding = True
        # this message will replace ok/fail message
        await self._print("SUT not responding", color=self.RED)

    async def kernel_panic(self) -> None:
        self._kernel_panic = True
        # this message will replace ok/fail message
        await self._print("kernel panic", color=self.RED)

    async def kernel_tainted(self, message: str) -> None:
        self._kernel_tainted = message

    async def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True
        # this message will replace ok/fail message
        await self._print("timed out", color=self.RED)

    async def test_started(self, test: Test) -> None:
        await self._print(f"{test.name}: ", color=self.WHITE, end="")

    async def test_completed(self, results: TestResults) -> None:
        if self._timed_out or self._sut_not_responding or self._kernel_panic:
            self._sut_not_responding = False
            self._kernel_panic = False
            self._timed_out = False
            return

        msg, col = self._result_color(results)
        await self._print(msg, color=col, end="")

        if self._kernel_tainted:
            await self._print(" | ", end="")
            await self._print("tainted", color=self.YELLOW, end="")
            self._kernel_tainted = None

        uf_time = self._user_friendly_duration(results.exec_time)
        await self._print(f"  ({uf_time})")


class VerboseUserInterface(ConsoleUserInterface):
    """
    Verbose console based user interface.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._timed_out = False

        libkirk.events.register("sut_stdout", self.sut_stdout)
        libkirk.events.register("kernel_tainted", self.kernel_tainted)
        libkirk.events.register("test_timed_out", self.test_timed_out)
        libkirk.events.register("test_started", self.test_started)
        libkirk.events.register("test_completed", self.test_completed)
        libkirk.events.register("test_stdout", self.test_stdout)

    async def sut_stdout(self, _: str, data: str) -> None:
        await self._print(data, end="")

    async def kernel_tainted(self, message: str) -> None:
        await self._print(f"Tainted kernel: {message}", color=self.YELLOW)

    async def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    async def test_started(self, test: Test) -> None:
        await self._print_section(test.name)
        await self._print("Executing: ", end="")
        await self._print(test.full_command, end="\n\n")

    async def test_completed(self, results: TestResults) -> None:
        if self._timed_out:
            await self._print("Test timed out", color=self.RED)

        self._timed_out = False

        parts = []

        if "Summary:" not in results.stdout:
            parts.extend(
                [
                    "\nSummary:",
                    f"passed    {results.passed}",
                    f"failed    {results.failed}",
                    f"broken    {results.broken}",
                    f"skipped   {results.skipped}",
                    f"warnings  {results.warnings}",
                ]
            )

        uf_time = self._user_friendly_duration(results.exec_time)
        parts.append(f"\nDuration: {uf_time}\n")

        await self._print("\n".join(parts))

    async def test_stdout(self, _: Test, data: str) -> None:
        await self._print(data, end="")


class ParallelUserInterface(ConsoleUserInterface):
    """
    Console based user interface for parallel execution of the tests.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted: Optional[str] = None
        self._timed_out = False
        self._pl_total = 0
        self._pl_done = 0

        libkirk.events.register("sut_not_responding", self.sut_not_responding)
        libkirk.events.register("kernel_panic", self.kernel_panic)
        libkirk.events.register("kernel_tainted", self.kernel_tainted)
        libkirk.events.register("suite_started", self.print_parallel)
        libkirk.events.register("test_timed_out", self.test_timed_out)
        libkirk.events.register("test_completed", self.test_completed)

    async def sut_not_responding(self) -> None:
        self._sut_not_responding = True

    async def kernel_panic(self) -> None:
        self._kernel_panic = True

    async def kernel_tainted(self, message: str) -> None:
        self._kernel_tainted = message

    async def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    async def print_parallel(self, suite: Suite) -> None:
        parallel_tests = [
            f"• {test.name}" for test in suite.tests if test.parallelizable
        ]

        if parallel_tests:
            self._pl_total += len(parallel_tests)
            await self._print("Following tests will run in parallel:")
            await self._print("\n".join(parallel_tests), end="\n\n")

    async def test_completed(self, results: TestResults) -> None:
        if results.test.parallelizable:
            self._pl_done += 1

            await self._print(
                f"{results.test.name} ({self._pl_done}/{self._pl_total}): ", end=""
            )
        else:
            await self._print(f"{results.test.name}: ", end="")

        if self._timed_out:
            await self._print("timed out", color=self.RED)
        elif self._sut_not_responding:
            # this message will replace ok/fail message
            await self._print("SUT not responding", color=self.RED)
        elif self._kernel_panic:
            # this message will replace ok/fail message
            await self._print("kernel panic", color=self.RED)
        else:
            msg, col = self._result_color(results)
            if self._kernel_tainted:
                await self._print(" | ", end="")
                await self._print("tainted", color=self.YELLOW, end="")

            uf_time = self._user_friendly_duration(results.exec_time)
            await self._print(f"  ({uf_time})")

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False
