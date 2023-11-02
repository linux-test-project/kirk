"""
.. module:: liburing
    :platform: Linux
    :synopsis: liburing framework implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import shlex
import logging
from libkirk.sut import SUT
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.results import ResultStatus
from libkirk.framework import Framework
from libkirk.framework import FrameworkError


class Liburing(Framework):
    """
    liburing testing suite integration class.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("libkirk.liburing")
        self._root = "/opt/liburing/test"

    @property
    def name(self) -> str:
        return "liburing"

    @property
    def config_help(self) -> dict:
        return {
            "root": "liburing test folder"
        }

    def setup(self, **kwargs: dict) -> None:
        root = kwargs.get("root", None)
        if root:
            self._root = root

    async def get_suites(self, sut: SUT) -> list:
        if not sut:
            raise ValueError("SUT is None")

        return ["default"]

    async def _read_tests(self, sut: SUT) -> list:
        """
        Read from Makefile which tests can be executed.
        """
        ret = await sut.run_command(f"test -d {self._root}")
        if ret["returncode"] != 0:
            raise FrameworkError(
                f"liburing test folder doesn't exist: {self._root}")

        self._logger.info("Reading available tests")
        ret = await sut.run_command(
            r"make -pnB | grep -E '^test_targets\s:?=\s'",
            cwd=self._root)

        stdout = ret["stdout"]
        if ret["returncode"] != 0:
            raise FrameworkError(f"Can't read liburing tests list: {stdout}")

        match = re.search(r'test_targets\s:?=\s(?P<tests>.*)', stdout)
        if not match:
            raise FrameworkError(f"Can't read liburing tests list: {stdout}")

        tests = match.group('tests').strip().split(' ')
        self._logger.debug("tests=%s", tests)

        return tests

    @staticmethod
    async def _is_parallelizable(sut: SUT, cmd: str) -> bool:
        """
        Return true if test can run in parallel.
        """
        parallel = True

        test_src = f"{cmd}.c"
        ret = await sut.run_command(f"test -f {test_src}")
        if ret["returncode"] != 0:
            test_src = f"{cmd}.cc"

        ret = await sut.run_command(f"test -f {test_src}")
        if ret["returncode"] != 0:
            return False

        # we try to be as more defensive as possible, so we exclude tests that:
        # - open sockets. We don't want to connect to the same socket
        # - open threads. We don't want to saturate the CPUs
        # - open files. We don't want to open the same file
        ret = await sut.run_command(
            f"grep -E 'socket.h|pthread.h|open\\(' {test_src}")
        if ret["returncode"] == 0:
            parallel = False

        return parallel

    async def find_command(self, sut: SUT, command: str) -> Test:
        if not sut:
            raise ValueError("SUT is None")

        if not command:
            raise ValueError("command is empty")

        cmd_args = shlex.split(command)
        cwd = None
        env = None

        ret = await sut.run_command(f"test -d {self._root}")
        if ret["returncode"] == 0:
            cwd = self._root
            env={"PATH": self._root}

        test = Test(
            name=cmd_args[0],
            cmd=cmd_args[0],
            args=cmd_args[1:] if len(cmd_args) > 0 else None,
            cwd=cwd,
            env=env,
            parallelizable=False)

        return test

    async def find_suite(self, sut: SUT, name: str) -> Suite:
        if not sut:
            raise ValueError("SUT is None")

        if not name:
            raise ValueError("name is empty")

        ret = await sut.run_command(f"test -d {self._root}")
        if ret["returncode"] != 0:
            raise FrameworkError(
                f"liburing test folder doesn't exist: {self._root}")

        tests = await self._read_tests(sut)
        tests_obj = []

        for test in tests:
            if not test:
                continue

            cmd = os.path.join(self._root, test)

            ret = await sut.run_command(f"test -f {cmd}")
            if ret["returncode"] != 0:
                continue

            parallelizable = await self._is_parallelizable(sut, cmd)

            # we really want to use binaries in the liburing/test folder
            # so we use the '<cwd>/test' notation. The reason is that some
            # tests have the same name of bash commands and SUT will execute
            # them instead.
            tests_obj.append(Test(
                name=test,
                cmd=os.path.join(self._root, test),
                cwd=self._root,
                parallelizable=parallelizable))

        suite = Suite("default", tests_obj)
        return suite

    async def read_result(
            self,
            test: Test,
            stdout: str,
            retcode: int,
            exec_t: float) -> TestResults:
        passed = 0
        failed = 0
        broken = 0
        skipped = 0
        error = retcode == -1
        status = ResultStatus.PASS

        skip_msgs = re.findall(r'[Ss]kip(ped|ping)?', stdout.lower())
        if skip_msgs:
            skipped = len(skip_msgs)

        if retcode == 0:
            passed = 1
        elif retcode != 0 and not error:
            status = ResultStatus.FAIL
            failed = 1

        if error:
            status = ResultStatus.BROK
            broken = 1

        result = TestResults(
            test=test,
            passed=passed,
            failed=failed,
            broken=broken,
            skipped=skipped,
            warnings=0,
            exec_time=exec_t,
            retcode=retcode,
            stdout=stdout,
            status=status,
        )

        return result
