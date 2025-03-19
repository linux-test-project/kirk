"""
.. module:: ui
    :platform: Linux
    :synopsis: modules used to generate real-time data from the executor

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import json
import asyncio
import logging
import libkirk
from libkirk.io import AsyncFile
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.results import SuiteResults


# pylint: disable=missing-function-docstring
# pylint: disable=too-many-public-methods
class JSONFileMonitor:
    """
    Monitor the current executor status and it redirects events to a file
    using JSON format.
    """

    def __init__(self, path: str) -> None:
        """
        :param path: path of the file
        :type path: str
        """
        self._logging = logging.getLogger("libkirk.monitor")
        self._logging.info("File to monitor: %s", path)
        self._lock = asyncio.Lock()

        self._path = path
        self._events = {
            "session_restore": self.session_restore,
            "session_started": self.session_started,
            "session_stopped": self.session_stopped,
            "sut_stdout": self.sut_stdout,
            "sut_start": self.sut_start,
            "sut_stop": self.sut_stop,
            "sut_restart": self.sut_restart,
            "sut_not_responding": self.sut_not_responding,
            "run_cmd_start": self.run_cmd_start,
            "run_cmd_stop": self.run_cmd_stop,
            "test_stdout": self.test_stdout,
            "test_started": self.test_started,
            "test_completed": self.test_completed,
            "test_timed_out": self.test_timed_out,
            "suite_started": self.suite_started,
            "suite_completed": self.suite_completed,
            "suite_timeout": self.suite_timeout,
            "session_warning": self.session_warning,
            "session_error": self.session_error,
            "kernel_panic": self.kernel_panic,
            "kernel_tainted": self.kernel_tainted
        }

    async def start(self) -> None:
        """
        Attach to events and start writing data inside the monitor file.
        """
        self._logging.info("Start monitoring")

        for name, coro in self._events.items():
            libkirk.events.register(name, coro)

    async def stop(self) -> None:
        """
        Stop monitoring events.
        """
        self._logging.info("Stop monitoring")

        for name, coro in self._events.items():
            libkirk.events.unregister(name, coro)

    async def _write(self, msg_type: str, msg: str) -> None:
        """
        Write a message to the JSON file.
        """
        data = {
            "type": msg_type,
            "message": msg,
        }

        data_str = json.dumps(data)

        async with self._lock:
            async with AsyncFile(self._path, 'w') as fdata:
                await fdata.write(data_str)

    @staticmethod
    def _test_to_dict(test: Test) -> dict:
        """
        Convert test into a dict which can be converted to JSON.
        """
        data = {
            "name": test.name,
            "command": test.command,
            "arguments": test.arguments,
            "parallelizable": test.parallelizable,
            "cwd": test.cwd,
            "env": test.env,
        }

        return data

    def _suite_to_dict(self, suite: Suite) -> dict:
        """
        Translate suite into a dict which can be converted into JSON.
        """
        data = {
            "name": suite.name,
            "tests": {}
        }

        tests = []
        for test in suite.tests:
            tests.append(self._test_to_dict(test))

        data["tests"] = tests

        return data

    async def session_restore(self, restore: str) -> None:
        await self._write("session_restore", {"restore": restore})

    async def session_started(self, tmpdir: str) -> None:
        await self._write("session_started", {"tmpdir": tmpdir})

    async def session_stopped(self) -> None:
        await self._write("session_stopped", {})

    async def sut_stdout(self, sut: str, data: str) -> None:
        await self._write("sut_stdout", {
            "sut": sut,
            "data": data,
        })

    async def sut_start(self, sut: str) -> None:
        await self._write("sut_start", {"sut": sut})

    async def sut_stop(self, sut: str) -> None:
        await self._write("sut_stop", {"sut": sut})

    async def sut_restart(self, sut: str) -> None:
        await self._write("sut_restart", {"sut": sut})

    async def sut_not_responding(self) -> None:
        await self._write("sut_not_responding", {})

    async def run_cmd_start(self, cmd: str) -> None:
        await self._write("run_cmd_start", {"cmd": cmd})

    async def run_cmd_stop(
            self,
            command: str,
            stdout: str,
            returncode: int) -> None:
        await self._write("run_cmd_stop", {
            "command": command,
            "stdout": stdout,
            "returncode": returncode,
        })

    async def test_stdout(self, test: Test, data: str) -> None:
        await self._write("test_stdout", {
            "test": self._test_to_dict(test),
            "data": data,
        })

    async def test_started(self, test: Test) -> None:
        await self._write("test_started", {
            "test": self._test_to_dict(test),
        })

    async def test_completed(self, results: TestResults) -> None:
        await self._write("test_completed", {
            "test": self._test_to_dict(results.test),
            "stdout": results.stdout,
            "status": results.status,
            "exec_time": results.exec_time,
            "passed": results.passed,
            "failed": results.failed,
            "broken": results.broken,
            "skipped": results.skipped,
            "warnings": results.warnings,
        })

    async def test_timed_out(self, test: Test, timeout: int) -> None:
        await self._write("test_started", {
            "test": self._test_to_dict(test),
            "timeout": timeout
        })

    async def suite_started(self, suite: Suite) -> None:
        await self._write("suite_started", self._suite_to_dict(suite))

    async def suite_completed(
            self,
            results: SuiteResults,
            exec_time: float) -> None:
        data = {
            "suite": self._suite_to_dict(results.suite),
            "exec_time": exec_time,
            "total_run": len(results.suite.tests),
            "passed": results.passed,
            "failed": results.failed,
            "skipped": results.skipped,
            "broken": results.broken,
            "warnings": results.warnings,
            "kernel_version": results.kernel,
            "cpu": results.cpu,
            "arch": results.arch,
            "ram": results.ram,
            "swap": results.swap,
            "distro": results.distro,
            "distro_version": results.distro_ver
        }

        await self._write("suite_completed", data)

    async def suite_timeout(self, suite: Suite, timeout: float) -> None:
        await self._write("suite_timeout", {
            "suite": self._suite_to_dict(suite),
            "timeout": timeout,
        })

    async def session_warning(self, msg: str) -> None:
        await self._write("session_warning", {"message": msg})

    async def session_error(self, error: str) -> None:
        await self._write("session_error", {"error": error})

    async def kernel_panic(self) -> None:
        await self._write("kernel_panic", {})

    async def kernel_tainted(self, message: str) -> None:
        await self._write("kernel_tainted", {"message": message})
