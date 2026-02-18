"""
.. module:: ltp
    :platform: Linux
    :synopsis: LTP framework definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import json
import logging
import os
import re
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from libkirk.com import ComChannel
from libkirk.data import (
    Suite,
    Test,
)
from libkirk.errors import FrameworkError
from libkirk.framework import Framework
from libkirk.results import (
    ResultStatus,
    TestResults,
)

# Mapping from LTP return code to ResultStatus
_RETCODE_STATUS: Dict[int, int] = {
    0: ResultStatus.PASS,
    2: ResultStatus.BROK,
    -1: ResultStatus.BROK,
    4: ResultStatus.WARN,
    32: ResultStatus.CONF,
}

_ANSI_ESCAPE = re.compile(r"\u001b\[[0-9;]+[a-zA-Z]")

_SUMMARY_RE = re.compile(
    r"Summary:\n"
    r"passed\s*(?P<passed>\d+)\n"
    r"failed\s*(?P<failed>\d+)\n"
    r"broken\s*(?P<broken>\d+)\n"
    r"skipped\s*(?P<skipped>\d+)\n"
    r"warnings\s*(?P<warnings>\d+)\n",
)


class LTPFramework(Framework):
    """
    Linux Test Project framework definition.
    """

    # Tags whose presence marks a test as non-parallelizable.
    PARALLEL_BLACKLIST: frozenset = frozenset(
        {
            "needs_root",
            "needs_device",
            "mount_device",
            "mntpoint",
            "resource_file",
            "format_device",
            "save_restore",
            "max_runtime",
        }
    )

    # Environment variables without the `LTP_` prefix that are still forwarded.
    SUPPORTED_ENV: frozenset = frozenset(
        {
            "PATH",
            "KCONFIG_PATH",
            "KCONFIG_SKIP_CHECK",
        }
    )

    # Variables set explicitly in _update_env_vars; skip them in the loop.
    _PRESET_ENV: frozenset = frozenset(
        {
            "LTPROOT",
            "TMPDIR",
            "LTP_COLORIZE_OUTPUT",
            "LTP_TIMEOUT_MUL",
        }
    )

    def __init__(
        self,
        max_runtime: float = 0.0,
        timeout: float = 30.0,
    ) -> None:
        """
        :param max_runtime: filter out all tests above this time value
        :type max_runtime: float
        :param timeout: generic tests timeout
        :type timeout: float
        """
        self._logger = logging.getLogger("libkirk.ltp")
        self._cmd_matcher = re.compile(r'(?:"[^"]*"|\'[^\']*\'|\S+)')
        self._max_runtime = max_runtime
        self._root = os.environ.get("LTPROOT", "/opt/ltp")
        self._tc_folder = os.path.join(self._root, "testcases", "bin")
        self._env: Dict[str, str] = {}

        self._update_env_vars(timeout)

    def _update_env_vars(self, timeout: float) -> None:
        """
        Populate self._env with LTP-relevant environment variables.
        """
        self._env["LTPROOT"] = self._root
        self._env["TMPDIR"] = os.environ.get("TMPDIR", "/tmp")
        self._env["LTP_COLORIZE_OUTPUT"] = os.environ.get("LTP_COLORIZE_OUTPUT", "1")

        multiplier = os.environ.get("LTP_TIMEOUT_MUL")
        if multiplier:
            self._env["LTP_TIMEOUT_MUL"] = multiplier
        elif timeout:
            self._env["LTP_TIMEOUT_MUL"] = str((timeout * 0.9) / 300.0)

        for key, val in os.environ.items():
            if key in self._PRESET_ENV:
                continue

            if key in self.SUPPORTED_ENV or key.startswith("LTP_"):
                self._env[key] = val

    async def _read_path(self, channel: ComChannel) -> Dict[str, str]:
        """
        Return a copy of self._env with the testcases folder appended to PATH.
        """
        env = self._env.copy()
        if "PATH" in env:
            env["PATH"] = f"{env['PATH']}:{self._tc_folder}"
        else:
            ret = await channel.run_command("echo -n $PATH")

            if not ret or ret["returncode"] != 0:
                raise FrameworkError("Can't read PATH variable")

            env["PATH"] = f"{ret['stdout'].strip()}:{self._tc_folder}"

        self._logger.debug("PATH=%s", env["PATH"])

        return env

    def _is_addable(self, test_params: Dict[str, Any]) -> bool:
        """
        Return False when max_runtime filtering is active and the test exceeds
        the configured limit.
        """
        if not self._max_runtime:
            return True

        runtime = test_params.get("max_runtime")
        if runtime is None:
            return True

        try:
            if float(runtime) >= self._max_runtime:
                self._logger.info("max_runtime is bigger than %f", self._max_runtime)

                return False
        except TypeError:
            self._logger.error("metadata contains wrong max_runtime type: %s", runtime)

        return True

    def _get_cmd_args(self, line: str) -> List[str]:
        """
        Split a runtest line into a list of command + arguments.

        Handles quoted arguments, e.g.::

            cmd -c "cmd2 -g arg1 -t arg2"
        """
        return self._cmd_matcher.findall(line)

    async def _read_runtest(
        self,
        channel: ComChannel,
        suite_name: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> Suite:
        """
        Parse a runtest file and return the corresponding Suite.
        """
        self._logger.info("collecting testing suite: %s", suite_name)

        metadata_tests: Optional[dict] = None
        if metadata:
            self._logger.info("Reading metadata content")
            metadata_tests = metadata.get("tests")

        env = await self._read_path(channel)
        tests: List[Test] = []

        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            self._logger.debug("Test declaration: %s", line)

            parts = self._get_cmd_args(line)
            if len(parts) < 2:
                raise FrameworkError("runtest file is not defining test command")

            test_name, test_cmd, *test_args = parts
            parallelizable = False

            if metadata_tests is not None:
                test_params = metadata_tests.get(test_name)
                if test_params is None:
                    # Test not using the new LTP API – parallelism unknown.
                    self._logger.info("Found %s test params in metadata", test_name)
                else:
                    self._logger.info("Found %s test params in metadata", test_name)
                    self._logger.debug("params=%s", test_params)

                    if not self._is_addable(test_params):
                        continue

                    parallelizable = not (self.PARALLEL_BLACKLIST & test_params.keys())

            self._logger.info(
                "Test '%s' is%s parallelizable",
                test_name,
                "" if parallelizable else " not",
            )

            test = Test(
                name=test_name,
                cmd=test_cmd,
                args=test_args,
                cwd=self._tc_folder,
                env=env,
                parallelizable=parallelizable,
            )
            tests.append(test)

            self._logger.debug("test: %s", test)

        self._logger.debug("Collected tests: %d", len(tests))

        suite = Suite(suite_name, tests)
        self._logger.debug(suite)
        self._logger.info("Collected testing suite: %s", suite_name)

        return suite

    async def get_suites(self, channel: ComChannel) -> List[str]:
        if not channel:
            raise ValueError("SUT is None")

        ret = await channel.run_command(f"test -d {self._root}")
        if not ret or ret["returncode"] != 0:
            raise FrameworkError(f"LTP folder doesn't exist: {self._root}")

        runtest_dir = os.path.join(self._root, "runtest")
        ret = await channel.run_command(f"test -d {runtest_dir}")
        if not ret or ret["returncode"] != 0:
            raise FrameworkError(f"'{runtest_dir}' doesn't exist inside SUT")

        ret = await channel.run_command(f"ls --format=single-column {runtest_dir}")
        if not ret:
            raise FrameworkError("Can't communicate with SUT")

        stdout = ret["stdout"]
        if ret["returncode"] != 0:
            raise FrameworkError(f"command failed with: {stdout}")

        return [line for line in stdout.split("\n") if line]

    async def find_command(self, channel: ComChannel, command: str) -> Test:
        if not channel:
            raise ValueError("SUT is None")
        if not command:
            raise ValueError("command is empty")

        cmd_args = self._get_cmd_args(command)
        cwd = None
        env = None

        ret = await channel.run_command(f"test -d {self._tc_folder}")
        if ret and ret["returncode"] == 0:
            cwd = self._tc_folder
            env = await self._read_path(channel)

        return Test(
            name=cmd_args[0],
            cmd=cmd_args[0],
            args=cmd_args[1:] or None,
            cwd=cwd,
            env=env,
            parallelizable=False,
        )

    async def find_suite(self, channel: ComChannel, name: str) -> Suite:
        if not channel:
            raise ValueError("SUT is None")
        if not name:
            raise ValueError("name is empty")

        ret = await channel.run_command(f"test -d {self._root}")
        if not ret or ret["returncode"] != 0:
            raise FrameworkError(f"LTP folder doesn't exist: {self._root}")

        suite_path = os.path.join(self._root, "runtest", name)
        ret = await channel.run_command(f"test -f {suite_path}")
        if not ret or ret["returncode"] != 0:
            raise FrameworkError(f"'{name}' suite doesn't exist")

        runtest_str = (await channel.fetch_file(suite_path)).decode(
            encoding="utf-8", errors="ignore"
        )

        metadata_dict = None
        metadata_path = os.path.join(self._root, "metadata", "ltp.json")
        ret = await channel.run_command(f"test -f {metadata_path}")
        if ret and ret["returncode"] == 0:
            metadata_dict = json.loads(await channel.fetch_file(metadata_path))

        return await self._read_runtest(channel, name, runtest_str, metadata_dict)

    async def read_result(
        self, test: Test, stdout: str, retcode: int, exec_t: float
    ) -> TestResults:
        stdout = _ANSI_ESCAPE.sub("", stdout)

        match = _SUMMARY_RE.search(stdout)
        if match:
            passed = int(match.group("passed"))
            failed = int(match.group("failed"))
            broken = int(match.group("broken"))
            skipped = int(match.group("skipped"))
            warnings = int(match.group("warnings"))
        else:
            passed = stdout.count("TPASS")
            failed = stdout.count("TFAIL")
            skipped = stdout.count("TSKIP")
            broken = stdout.count("TBROK")
            warnings = stdout.count("TWARN")

            if not any((passed, failed, skipped, broken, warnings)):
                # Legacy test: derive counts from the return code alone.
                if retcode == 0:
                    passed = 1
                elif retcode == 4:
                    warnings = 1
                elif retcode == 32:
                    skipped = 1
                elif retcode != -1:
                    failed = 1

        status = _RETCODE_STATUS.get(retcode, ResultStatus.FAIL)

        if retcode == -1:
            broken = 1

        return TestResults(
            test=test,
            failed=failed,
            passed=passed,
            broken=broken,
            skipped=skipped,
            warnings=warnings,
            exec_time=exec_t,
            retcode=retcode,
            stdout=stdout,
            status=status,
        )
