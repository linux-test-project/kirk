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
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"
        elif minutes > 0:
            return f"{minutes:.0f}m {seconds:.0f}s"
        else:
            return f"{seconds:.3f}s"

    async def session_restore(self, restore: str) -> None:
        await self._print(f"Restore session: {restore}")

    async def session_started(self, tmpdir: str) -> None:
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
        await self._print(f"Connecting to SUT: {sut}")

    async def sut_stop(self, sut: str) -> None:
        await self._print(f"\nDisconnecting from SUT: {sut}")

    async def sut_restart(self, sut: str) -> None:
        await self._print(f"Restarting SUT: {sut}")

    async def run_cmd_start(self, cmd: str) -> None:
        await self._print(f"{cmd}", color=self.CYAN)

    async def run_cmd_stdout(self, data: str) -> None:
        await self._print(data, end="")

    async def run_cmd_stop(self, command: str, stdout: str, returncode: int) -> None:
        await self._print(f"\nExit code: {returncode}\n")

    async def suite_started(self, suite: Suite) -> None:
        suite_msg = f"\nStarting suite: {suite.name}"
        message = f"{suite_msg}\n{'-' * len(suite_msg)}"
        await self._print(message)

    async def suite_completed(self, results: SuiteResults, exec_time: float) -> None:
        duration = self._user_friendly_duration(results.exec_time)
        exec_time_uf = self._user_friendly_duration(exec_time)

        message = (
            f"{' ' * 128}\n"
            f"Execution time: {exec_time_uf}\n\n"
            f"\tSuite:         {results.suite.name}\n"
            f"\tTotal runs:    {len(results.suite.tests)}\n"
            f"\tRuntime:       {duration}\n"
            f"\tPassed:        {results.passed}\n"
            f"\tFailed:        {results.failed}\n"
            f"\tSkipped:       {results.skipped}\n"
            f"\tBroken:        {results.broken}\n"
            f"\tWarnings:      {results.warnings}\n"
            f"\tKernel:        {results.kernel}\n"
            f"\t/proc/cmdline: {results.cmdline}\n"
            f"\tMachine:       {results.cpu}\n"
            f"\tArch:          {results.arch}\n"
            f"\tRAM:           {results.ram}\n"
            f"\tSwap:          {results.swap}\n"
            f"\tDistro:        {results.distro} {results.distro_ver}"
        )

        await self._print(message)

    async def suite_timeout(self, suite: Suite, timeout: float) -> None:
        await self._print(
            f"Suite '{suite.name}' timed out after {timeout} seconds", color=self.RED
        )

    async def session_warning(self, msg: str) -> None:
        await self._print(f"Warning: {msg}", color=self.YELLOW)

    async def session_error(self, error: str) -> None:
        await self._print(f"Error: {error}", color=self.RED)

    async def session_completed(self, results: List[SuiteResults]) -> None:
        if len(results) < 2:
            return

        num_runs = sum(len(result.tests_results) for result in results)
        passed = sum(result.passed for result in results)
        failed = sum(result.failed for result in results)
        skipped = sum(result.skipped for result in results)
        broken = sum(result.broken for result in results)
        warnings = sum(result.warnings for result in results)
        exec_time = sum(result.exec_time for result in results)
        exec_time_uf = self._user_friendly_duration(exec_time)

        message = (
            f"\nSuites completed: {len(results)}\n\n"
            f"\tTotal runs:  {num_runs}\n"
            f"\tRuntime:    {exec_time_uf}\n"
            f"\tPassed:     {passed}\n"
            f"\tFailed:     {failed}\n"
            f"\tSkipped:    {skipped}\n"
            f"\tBroken:     {broken}\n"
            f"\tWarnings:   {warnings}"
        )

        await self._print(message)

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

        if results.failed > 0:
            msg, col = "fail", self.RED
        elif results.skipped > 0:
            msg, col = "skip", self.YELLOW
        elif results.broken > 0:
            msg, col = "broken", self.CYAN
        else:
            msg, col = "pass", self.GREEN

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
        await self._print("\n===== ", end="")
        await self._print(test.name, color=self.CYAN, end="")
        await self._print(" =====")
        await self._print("command: ", end="")
        await self._print(test.full_command)

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
            f"- {test.name}" for test in suite.tests if test.parallelizable
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
            if results.failed > 0:
                msg, col = "fail", self.RED
            elif results.skipped > 0:
                msg, col = "skip", self.YELLOW
            elif results.broken > 0:
                msg, col = "broken", self.CYAN
            else:
                msg, col = "pass", self.GREEN

            await self._print(msg, color=col, end="")

            if self._kernel_tainted:
                await self._print(" | ", end="")
                await self._print("tainted", color=self.YELLOW, end="")

            uf_time = self._user_friendly_duration(results.exec_time)
            await self._print(f"  ({uf_time})")

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False
