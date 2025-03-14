"""
.. module:: ui
    :platform: Linux
    :synopsis: module that contains user interface

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import platform
import traceback
import libkirk
import libkirk.events
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.results import SuiteResults

# pylint: disable=missing-function-docstring
# pylint: disable=unused-argument


class ConsoleUserInterface:
    """
    Console based user interface.
    """

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

        libkirk.events.register("session_restore", self.session_restore)
        libkirk.events.register("session_started", self.session_started)
        libkirk.events.register("session_stopped", self.session_stopped)
        libkirk.events.register("sut_start", self.sut_start)
        libkirk.events.register("sut_stop", self.sut_stop)
        libkirk.events.register("sut_restart", self.sut_restart)
        libkirk.events.register("run_cmd_start", self.run_cmd_start)
        libkirk.events.register("run_cmd_stdout", self.run_cmd_stdout)
        libkirk.events.register("run_cmd_stop", self.run_cmd_stop)
        libkirk.events.register("suite_started", self.suite_started)
        libkirk.events.register("suite_completed", self.suite_completed)
        libkirk.events.register("suite_timeout", self.suite_timeout)
        libkirk.events.register("session_warning", self.session_warning)
        libkirk.events.register("session_error", self.session_error)
        libkirk.events.register("internal_error", self.internal_error)

        # we register a special event 'printf' with ordered coroutines,
        # so we ensure that print threads will be executed one after the
        # other and user interface will be printed in the correct way
        libkirk.events.register("printf", self.print_message, ordered=True)

    async def _print(self, msg: str, color: str = None, end: str = "\n"):
        """
        Fire a `printf` event.
        """
        msg = msg.replace(self.RESET_SCREEN, '')
        msg = msg.replace('\r', '')

        if color and not self._no_colors:
            msg = f"{color}{msg}{self.RESET_COLOR}"

        await libkirk.events.fire("printf", msg, end=end, flush=True)

    async def print_message(self, msg: str, end: str = "\n", flush: bool = True):
        """
        Print a message in console, avoiding any I/O blocking operation
        done by the `print` built-in function, using `asyncio.to_thread()`.
        """
        def _wrap():
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
        uf_time = ""

        if hours > 0:
            uf_time = f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"
        elif minutes > 0:
            uf_time = f"{minutes:.0f}m {seconds:.0f}s"
        else:
            uf_time = f"{seconds:.3f}s"

        return uf_time

    async def session_restore(self, restore: str) -> None:
        await self._print(f"Restore session: {restore}")

    async def session_started(self, tmpdir: str) -> None:
        uname = platform.uname()
        message = "Host information\n\n"
        message += f"\tSystem: {uname.system}\n"
        message += f"\tNode: {uname.node}\n"
        message += f"\tKernel Release: {uname.release}\n"
        message += f"\tKernel Version: {uname.version}\n"
        message += f"\tMachine Architecture: {uname.machine}\n"
        message += f"\tProcessor: {uname.processor}\n"
        message += f"\n\tTemporary directory: {tmpdir}\n"

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
        await self._print(data, end='')

    async def run_cmd_stop(
            self,
            command: str,
            stdout: str,
            returncode: int) -> None:
        await self._print(f"\nExit code: {returncode}\n")

    async def suite_started(self, suite: Suite) -> None:
        await self._print(f"Starting suite: {suite.name}")

    async def suite_completed(
            self,
            results: SuiteResults,
            exec_time: float) -> None:
        duration = self._user_friendly_duration(results.exec_time)
        exec_time_uf = self._user_friendly_duration(exec_time)

        message = "\n"
        message += " " * 128 + "\n"
        message += f"Execution time: {exec_time_uf}\n"
        message += "\n"
        message += f"Suite Name: {results.suite.name}\n"
        message += f"Total Run: {len(results.suite.tests)}\n"
        message += f"Total Runtime: {duration}\n"
        message += f"Passed Tests: {results.passed}\n"
        message += f"Failed Tests: {results.failed}\n"
        message += f"Skipped Tests: {results.skipped}\n"
        message += f"Broken Tests: {results.broken}\n"
        message += f"Warnings: {results.warnings}\n"
        message += f"Kernel Version: {results.kernel}\n"
        message += f"CPU: {results.cpu}\n"
        message += f"Machine Architecture: {results.arch}\n"
        message += f"RAM: {results.ram}\n"
        message += f"Swap memory: {results.swap}\n"
        message += f"Distro: {results.distro}\n"
        message += f"Distro Version: {results.distro_ver}\n"

        await self._print(message)

    async def suite_timeout(self, suite: Suite, timeout: float) -> None:
        await self._print(
            f"Suite '{suite.name}' timed out after {timeout} seconds",
            color=self.RED)

    async def session_warning(self, msg: str) -> None:
        await self._print(f"Warning: {msg}", color=self.YELLOW)

    async def session_error(self, error: str) -> None:
        await self._print(f"Error: {error}", color=self.RED)

    async def internal_error(self, exc: BaseException, func_name: str) -> None:
        await self._print(
            f"\nUI error in function '{func_name}': {exc}\n",
            color=self.RED)

        traceback.print_exc()


class SimpleUserInterface(ConsoleUserInterface):
    """
    Console based user interface without many fancy stuff.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
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
        await self._print(f"{test.name}: ", end="")

    async def test_completed(self, results: TestResults) -> None:
        if self._timed_out or self._sut_not_responding or self._kernel_panic:
            self._sut_not_responding = False
            self._kernel_panic = False
            self._timed_out = False
            return

        msg = "pass"
        col = self.GREEN

        if results.failed > 0:
            msg = "fail"
            col = self.RED
        elif results.skipped > 0:
            msg = "skip"
            col = self.YELLOW
        elif results.broken > 0:
            msg = "broken"
            col = self.CYAN

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
        await self._print(data, end='')

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

        if "Summary:" not in results.stdout:
            await self._print("\nSummary:")
            await self._print(f"passed    {results.passed}")
            await self._print(f"failed    {results.failed}")
            await self._print(f"broken    {results.broken}")
            await self._print(f"skipped   {results.skipped}")
            await self._print(f"warnings  {results.warnings}")

        uf_time = self._user_friendly_duration(results.exec_time)
        await self._print(f"\nDuration: {uf_time}\n")

    async def test_stdout(self, _: Test, data: str) -> None:
        await self._print(data, end='')


class ParallelUserInterface(ConsoleUserInterface):
    """
    Console based user interface for parallel execution of the tests.
    """
    LINE_UP = '\033[1A'

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False
        self._running = []

        libkirk.events.register("sut_not_responding", self.sut_not_responding)
        libkirk.events.register("kernel_panic", self.kernel_panic)
        libkirk.events.register("kernel_tainted", self.kernel_tainted)
        libkirk.events.register("test_timed_out", self.test_timed_out)
        libkirk.events.register("test_started", self.test_started)
        libkirk.events.register("test_completed", self.test_completed)

    async def _refresh_running_tests(self) -> None:
        tests_num = len(self._running)

        await self._print(" " * 64, end='\r')
        await self._print("")
        await self._print(f"*** {tests_num} background test(s) ***")

        for test_name in self._running:
            await self._print(f"- {test_name}", end='')
            await self._print(" " * 32)

        # move back at the very beginning so the next time
        # we will override current running tests status
        for _ in range(tests_num + 2):
            await self._print(self.LINE_UP, end='')

    async def sut_not_responding(self) -> None:
        self._sut_not_responding = True

    async def kernel_panic(self) -> None:
        self._kernel_panic = True

    async def kernel_tainted(self, message: str) -> None:
        self._kernel_tainted = message

    async def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    async def test_started(self, test: Test) -> None:
        self._running.append(test.name)
        await self._refresh_running_tests()

    async def test_completed(self, results: TestResults) -> None:
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
            msg = "pass"
            col = self.GREEN

            if results.failed > 0:
                msg = "fail"
                col = self.RED
            elif results.skipped > 0:
                msg = "skip"
                col = self.YELLOW
            elif results.broken > 0:
                msg = "broken"
                col = self.CYAN

            await self._print(msg, color=col, end="")

            if self._kernel_tainted:
                await self._print(" | ", end="")
                await self._print("tainted", color=self.YELLOW, end="")

            uf_time = self._user_friendly_duration(results.exec_time)
            await self._print(f"  ({uf_time})", end='')
            # cleanup message that was there before
            await self._print(" " * 16)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False

        self._running.remove(results.test.name)
        await self._refresh_running_tests()
