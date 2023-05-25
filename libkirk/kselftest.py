"""
.. module:: kselftest
    :platform: Linux
    :synopsis: kselftest framework support

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import logging
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.framework import Framework


class KselftestFramework(Framework):
    """
    kselftest testing suite integration class.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("libkirk.kselftest")
        self._root = None

    @property
    def name(self) -> str:
        return "kselftest"

    @property
    def config_help(self) -> dict:
        return {
            "root": "kselftest folder"
        }

    def setup(self, **kwargs: dict) -> None:
        self._root = kwargs.get("root", "/opt/linux/tools/testing/selftests")

    async def _get_cgroup(self, sut: SUT) -> Suite:
        """
        Return a cgroup testing suite.
        """
        self._logger.info("Reading cgroup folder")
        cgroup_dir = os.path.join(self._root, "cgroup")

        ret = await sut.run_command(f"test -d {cgroup_dir}")
        if ret["returncode"] != 0:
            raise KirkException(
                f"cgroup folder is not available: {cgroup_dir}")

        ret = await sut.run_command(
            "basename -s .c -- test_*.c",
            cwd=cgroup_dir)
        if ret["returncode"] != 0 or not ret["stdout"]:
            raise KirkException("Can't read cgroup tests")

        names = ret["stdout"].split('\n')
        tests_obj = []

        for name in names:
            if not name:
                continue

            tests_obj.append(Test(
                name=name,
                cmd=os.path.join(cgroup_dir, name),
                cwd=cgroup_dir,
                parallelizable=False))

        suite = Suite(name="cgroup", tests=tests_obj)
        self._logger.debug("suite=%s", suite)

        return suite

    async def get_suites(self, sut: SUT) -> list:
        if not sut:
            raise ValueError("SUT is None")

        return ["cgroup"]

    async def find_suite(self, sut: SUT, name: str) -> Suite:
        if not sut:
            raise ValueError("SUT is None")

        if not name:
            raise ValueError("name is empty")

        ret = await sut.run_command(f"test -d {self._root}")
        if ret["returncode"] != 0:
            raise KirkException(
                f"kselftest folder doesn't exist: {self._root}")

        suite = None
        if name == "cgroup":
            suite = await self._get_cgroup(sut)
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

        if retcode == 0:
            passed = 1
        elif retcode == 4:
            skipped = 1
        elif retcode != 0 and not error:
            failed = 1

        if error:
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
        )

        return result
