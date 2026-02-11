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


class LTPFramework(Framework):
    """
    Linux Test Project framework definition.
    """

    PARALLEL_BLACKLIST = [
        "needs_root",
        "needs_device",
        "mount_device",
        "mntpoint",
        "resource_file",
        "format_device",
        "save_restore",
        "max_runtime",
    ]

    SUPPORTED_ENV = [
        "KCONFIG_PATH",
        "KCONFIG_SKIP_CHECK",
        "LTPROOT",
        "LTP_COLORIZE_OUTPUT",
        "LTP_DEV",
        "LTP_REPRODUCIBLE_OUTPUT",
        "LTP_SINGLE_FS_TYPE",
        "LTP_FORCE_SINGLE_FS_TYPE",
        "LTP_DEV_FS_TYPE",
        "LTP_TIMEOUT_MUL",
        "LTP_RUNTIME_MUL",
        "LTP_USR_UID",
        "LTP_USR_GID",
        "LTP_VIRT_OVERRIDE",
        "PATH",
        "TMPDIR",
        "LTP_NO_CLEANUP",
        "LTP_ENABLE_DEBUG",
        "LTP_IMA_LOAD_POLICY",
        "LTP_NFS_NETNS_USE_LO",
    ]

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
        self._env = {}

        self._update_env_vars(timeout)

    def _update_env_vars(self, timeout: float) -> None:
        """
        Update environment variables for LTP tests.
        """
        self._env["LTPROOT"] = self._root
        self._env["TMPDIR"] = os.environ.get("TMPDIR", "/tmp")
        self._env["LTP_COLORIZE_OUTPUT"] = os.environ.get("LTP_COLORIZE_OUTPUT", "1")

        multiplier = os.environ.get("LTP_TIMEOUT_MUL", None)
        if multiplier:
            self._env["LTP_TIMEOUT_MUL"] = multiplier
        else:
            if timeout:
                self._env["LTP_TIMEOUT_MUL"] = str((timeout * 0.9) / 300.0)

        for sup_env in self.SUPPORTED_ENV:
            if sup_env in self._env:
                continue

            if sup_env not in os.environ:
                continue

            self._env[sup_env] = os.environ[sup_env]

    async def _read_path(self, channel: ComChannel) -> Dict[str, str]:
        """
        Read PATH and initialize it with testcases folder as well.
        """
        env = self._env.copy()
        if "PATH" in env:
            env["PATH"] = env["PATH"] + f":{self._tc_folder}"
        else:
            ret = await channel.run_command("echo -n $PATH")
            if not ret or ret["returncode"] != 0:
                raise FrameworkError("Can't read PATH variable")

            env["PATH"] = ret["stdout"].strip() + f":{self._tc_folder}"

        self._logger.debug("PATH=%s", env["PATH"])

        return env

    def _is_addable(self, test_params: Dict[str, Any]) -> bool:
        """
        Check if test has to be added or not, according with test parameters
        from metadata.
        """
        addable = True

        # filter out max_runtime tests when required
        if self._max_runtime > 0:
            runtime = test_params.get("max_runtime")
            if runtime:
                try:
                    runtime = float(runtime)
                    if runtime >= self._max_runtime:
                        self._logger.info(
                            "max_runtime is bigger than %f", self._max_runtime
                        )
                        addable = False
                except TypeError:
                    self._logger.error(
                        "metadata contains wrong max_runtime type: %s", runtime
                    )

        return addable

    def _get_cmd_args(self, line: str) -> List[str]:
        """
        Return a command with arguments inside a list(str).
        The command can have the following syntax:
            1. cmd
            2. cmd -t myarg1 ..
            3. cmd myfolder=$TMPDIR/folder -t myarg1 ..
            4. cmd -c "cmd2 -g arg1 -t arg2" ..
        """
        matches = self._cmd_matcher.findall(line)
        parts = [match for match in matches if match]

        return parts

    async def _read_runtest(
        self,
        channel: ComChannel,
        suite_name: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> Suite:
        """
        It reads a runtest file content and it returns a Suite object.
        """
        self._logger.info("collecting testing suite: %s", suite_name)

        metadata_tests = None
        if metadata:
            self._logger.info("Reading metadata content")
            metadata_tests = metadata.get("tests", None)

        env = await self._read_path(channel)

        tests = []
        lines = content.split("\n")

        for line in lines:
            if not line.strip() or line.strip().startswith("#"):
                continue

            self._logger.debug("Test declaration: %s", line)

            parts = self._get_cmd_args(line)

            if len(parts) < 2:
                raise FrameworkError("runtest file is not defining test command")

            test_name = parts[0]
            test_cmd = parts[1]
            test_args = []

            if len(parts) >= 3:
                test_args = parts[2:]

            parallelizable = True

            if not metadata_tests:
                # no metadata no party
                parallelizable = False
            else:
                test_params = metadata_tests.get(test_name, None)
                if test_params:
                    self._logger.info("Found %s test params in metadata", test_name)
                    self._logger.debug("params=%s", test_params)

                if test_params is None:
                    # this probably means test is not using new LTP API,
                    # so we can't decide if test can run in parallel or not
                    parallelizable = False
                else:
                    if not self._is_addable(test_params):
                        continue

                    for blacklist_param in self.PARALLEL_BLACKLIST:
                        if blacklist_param in test_params:
                            parallelizable = False
                            break

            if not parallelizable:
                self._logger.info("Test '%s' is not parallelizable", test_name)
            else:
                self._logger.info("Test '%s' is parallelizable", test_name)

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
        if not ret or ret["returncode"] != 0:
            raise FrameworkError(f"command failed with: {stdout}")

        suites = [line for line in stdout.split("\n") if line]
        return suites

    async def find_command(self, channel: ComChannel, command: str) -> Test:
        if not channel:
            raise ValueError("SUT is None")

        if not command:
            raise ValueError("command is empty")

        cmd_args = self._get_cmd_args(command)
        args = cmd_args[1:] if cmd_args else None
        cwd = None
        env = None

        ret = await channel.run_command(f"test -d {self._tc_folder}")
        if ret and ret["returncode"] == 0:
            cwd = self._tc_folder
            env = await self._read_path(channel)

        test = Test(
            name=cmd_args[0],
            cmd=cmd_args[0],
            args=args,
            cwd=cwd,
            env=env,
            parallelizable=False,
        )

        return test

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

        runtest_data = await channel.fetch_file(suite_path)
        runtest_str = runtest_data.decode(encoding="utf-8", errors="ignore")

        metadata_path = os.path.join(self._root, "metadata", "ltp.json")
        metadata_dict = None
        ret = await channel.run_command(f"test -f {metadata_path}")
        if ret and ret["returncode"] == 0:
            metadata_data = await channel.fetch_file(metadata_path)
            metadata_dict = json.loads(metadata_data)

        suite = await self._read_runtest(channel, name, runtest_str, metadata_dict)

        return suite

    async def read_result(
        self, test: Test, stdout: str, retcode: int, exec_t: float
    ) -> TestResults:
        # get rid of colors from stdout
        stdout = re.sub(r"\u001b\[[0-9;]+[a-zA-Z]", "", stdout)

        match = re.search(
            r"Summary:\n"
            r"passed\s*(?P<passed>\d+)\n"
            r"failed\s*(?P<failed>\d+)\n"
            r"broken\s*(?P<broken>\d+)\n"
            r"skipped\s*(?P<skipped>\d+)\n"
            r"warnings\s*(?P<warnings>\d+)\n",
            stdout,
        )

        passed = 0
        failed = 0
        skipped = 0
        broken = 0
        skipped = 0
        warnings = 0
        error = retcode == -1
        status = ResultStatus.PASS

        if match:
            passed = int(match.group("passed"))
            failed = int(match.group("failed"))
            skipped = int(match.group("skipped"))
            broken = int(match.group("broken"))
            skipped = int(match.group("skipped"))
            warnings = int(match.group("warnings"))
        else:
            passed = stdout.count("TPASS")
            failed = stdout.count("TFAIL")
            skipped = stdout.count("TSKIP")
            broken = stdout.count("TBROK")
            warnings = stdout.count("TWARN")

            if (
                passed == 0
                and failed == 0
                and skipped == 0
                and broken == 0
                and warnings == 0
            ):
                # if no results are given, this is probably an
                # old test implementation that fails when return
                # code is != 0
                if retcode == 0:
                    passed = 1
                elif retcode == 4:
                    warnings = 1
                elif retcode == 32:
                    skipped = 1
                elif not error:
                    failed = 1

        if retcode == 0:
            status = ResultStatus.PASS
        elif retcode in (2, -1):
            status = ResultStatus.BROK
        elif retcode == 4:
            status = ResultStatus.WARN
        elif retcode == 32:
            status = ResultStatus.CONF
        else:
            status = ResultStatus.FAIL

        if error:
            broken = 1

        result = TestResults(
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

        return result
