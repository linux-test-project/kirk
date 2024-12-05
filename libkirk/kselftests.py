"""
.. module:: kselftests
    :platform: Linux
    :synopsis: kselftests framework support

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import re
import os
import shlex
import logging
import tempfile
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.results import ResultStatus
from libkirk.framework import Framework


class KselftestFramework(Framework):
    """
    kselftests testing suite integration class.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("libkirk.kselftests")
        self._root = None
        self._env = None

    @property
    def name(self) -> str:
        return "kselftests"

    @property
    def config_help(self) -> dict:
        return {
            "root": "kselftests folder"
        }

    def setup(self, **kwargs: dict) -> None:
        self._root = kwargs.get("root", "/opt/linux/tools/testing/selftests")
        self._env = {
            "KSELFTESTROOT": self._root,
        }

        env = kwargs.get("env", None)
        if env:
            self._env.update(env)

        if self._env["KSELFTESTROOT"]:
            self._root = self._env["KSELFTESTROOT"]

    async def _get_suite(self, sut: SUT, suite_name, suite_tests) -> Suite:
        """
        Return a subsuite from kselftest.
        """
        self._logger.info(f"Reading {suite_name} folder")
        suite_dir = os.path.join(self._root, suite_name)

        ret = await sut.run_command(f"test -d {suite_dir}")
        if ret["returncode"] != 0:
            raise KirkException(
                f"{suite_name} folder is not available: {suite_dir}")

        tests_obj = []

        with open(suite_tests.name) as file:
            for test_name in file:
                test_name = test_name.strip()
                if not test_name:
                    continue

                tests_obj.append(Test(
                    name=test_name,
                    cmd=os.path.join(suite_dir, test_name),
                    cwd=suite_dir,
                    parallelizable=False))

        suite = Suite(name=suite_name, tests=tests_obj)
        self._logger.debug("suite=%s", suite)

        return suite

    @property
    def name(self) -> str:
        return "kselftest"

    async def get_suites(self, sut: SUT) -> list:
        if not sut:
            raise ValueError("SUT is None")

        ret = await sut.run_command(f"test -d {self._root}")
        if ret["returncode"] != 0:
            raise KirkException(
                f"kselftests folder doesn't exist: {self._root}")

        suite_file = os.path.join(self._root, "kselftest-list.txt")
        ret = await sut.run_command(f"test -f {suite_file}")
        if ret["returncode"] != 0:
            raise FrameworkError(f"'{name}' suite doesn't exist")
        suite_tests = tempfile.NamedTemporaryFile()
        tests = ""
        suites = []
        with open(suite_file, 'r') as file:
            for line in file.readlines():
                name, _ = line.split(":")
                suites.append(name)

        # Make the list of suites unique.
        return list(dict.fromkeys(suites))

    async def find_command(self, sut: SUT, command: str) -> Test:
        if not sut:
            raise ValueError("SUT is None")

        if not command:
            raise ValueError("command is empty")

        cmd_args = shlex.split(command)
        suite_folder = None

        for suite in await self.get_suites(sut):
            folder = os.path.join(self._root, suite)
            binary = os.path.join(folder, cmd_args[0])

            ret = await sut.run_command(f"test -f {binary}")
            if ret["returncode"] == 0:
                suite_folder = folder
                break

        cwd = None
        env = None

        ret = await sut.run_command(f"test -d {suite_folder}")
        if ret["returncode"] == 0:
            cwd = suite_folder
            env={"PATH": suite_folder}

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
            raise KirkException(
                f"kselftests folder doesn't exist: {self._root}")

        suite_file = os.path.join(self._root, "kselftest-list.txt")
        ret = await sut.run_command(f"test -f {suite_file}")
        if ret["returncode"] != 0:
            raise FrameworkError(f"'{name}' suite doesn't exist")

        suite_tests = tempfile.NamedTemporaryFile()
        tests = ""
        with open(suite_file, 'r') as file:
            for line in file.readlines():
                if f"{name}:" in line:
                    name, test = line.split(":")
                    tests += f"{test.strip()}\n"

        with open(suite_tests.name, 'w') as f:
            f.write(tests)

        suite_path = os.path.join(self._root, name)
        suite = name
        if suite != "":
            suite = await self._get_suite(sut, name, suite_tests)
        else:
            raise KirkException(f"'{name}' suite is not available")

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

        if retcode == 0:
            status = ResultStatus.PASS
            passed = 1
        elif retcode == 4:
            status = ResultStatus.CONF
            skipped = 1
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
