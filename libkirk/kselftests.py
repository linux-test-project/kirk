"""
.. module:: kselftests
    :platform: Linux
    :synopsis: kselftests framework support

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import shlex
import logging
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

        names = [n.rstrip() for n in  ret["stdout"].split('\n')]
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

    async def _get_bpf(self, sut: SUT) -> Suite:
        """
        Return the eBPF testing suite. For now only covers test_progs.
        """
        bpf_dir = os.path.join(self._root, "bpf")

        ret = await sut.run_command(f"test -d {bpf_dir}")
        if ret["returncode"] != 0:
            raise KirkException(
                f"bpf folder is not available: {bpf_dir}")

        self._logger.info("Running eBPF %s/test_progs --list", bpf_dir)
        ret = await sut.run_command(
            "./test_progs --list",
            cwd=bpf_dir)
        if ret["returncode"] != 0 or not ret["stdout"]:
            raise KirkException("Can't list eBPF prog tests")

        names = [n.rstrip() for n in  ret["stdout"].split('\n')]
        tests_obj = []

        for name in names:
            if not name:
                continue

            tests_obj.append(Test(
                name=name,
                cmd="./test_progs",
                args=["-t", name],
                cwd=bpf_dir))

        suite = Suite(name="bpf", tests=tests_obj)
        self._logger.debug("suite=%s", suite)

        return suite

    async def get_suites(self, sut: SUT) -> list:
        if not sut:
            raise ValueError("SUT is None")

        return ["cgroup", "bpf"]

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

        suite = None
        if name == "cgroup":
            suite = await self._get_cgroup(sut)
        elif name == "bpf":
            suite = await self._get_bpf(sut)
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
