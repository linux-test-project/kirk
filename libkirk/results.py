"""
.. module:: results
    :platform: Linux
    :synopsis: module containing suites data definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import (
    List,
    Optional,
)

from libkirk.data import (
    Suite,
    Test,
)


class ResultStatus:
    """
    Overall status of the test. This is a specific flag that is used to
    recognize final test status. For example, we might have 10 tests passing
    inside a single test binary, but the overall status of the test is fine, so
    we assign a PASS status.
    """

    PASS = 0
    """
    Test has passed.
    """

    BROK = 2
    """
    Test is broken.
    """

    WARN = 4
    """
    Test warnings received.
    """

    FAIL = 16
    """
    Test has failed.
    """

    CONF = 32
    """
    Test can't run because of configuration error.
    """


class Results:
    """
    Base class for results.
    """

    @property
    def exec_time(self) -> float:
        """
        :return: Test execution time in seconds.
        :rtype: float
        """
        raise NotImplementedError()

    @property
    def failed(self) -> int:
        """
        :return: Number of failures.
        :rtype: int
        """
        raise NotImplementedError()

    @property
    def passed(self) -> int:
        """
        :return: Number of passed tests.
        :rtype: int
        """
        raise NotImplementedError()

    @property
    def broken(self) -> int:
        """
        :return: Number of broken tests.
        :rtype: int
        """
        raise NotImplementedError()

    @property
    def skipped(self) -> int:
        """
        :return: Number of skipped tests.
        :rtype: int
        """
        raise NotImplementedError()

    @property
    def warnings(self) -> int:
        """
        :return: Number of warnings.
        :rtype: int
        """
        raise NotImplementedError()


class TestResults(Results):
    """
    Test results definition.
    """

    def __init__(
        self,
        test: Test,
        failed: int = 0,
        passed: int = 0,
        broken: int = 0,
        skipped: int = 0,
        warnings: int = 0,
        exec_time: float = 0.0,
        status: int = ResultStatus.PASS,
        retcode: int = 0,
        stdout: str = "",
    ) -> None:
        """
        :param test: Test object declaration.
        :type test: Test
        :param failed: number of TFAIL.
        :type failed: int
        :param passed: number of TPASS.
        :type passed: int
        :param broken: number of TBROK.
        :type broken: int
        :param skipped: number of TSKIP.
        :type skipped: int
        :param warnings: number of TWARN.
        :type warnings: int
        :param exec_time: Time for test's execution.
        :type exec_time: float
        :param status: Overall status of the test.
        :type status: int
        :param retcode: Return code of the executed test.
        :type retcode: int
        :param stdout: Stdout of the test.
        :type stdout: str
        """
        if not test:
            raise ValueError("Empty test object")

        self._test = test
        self._failed = failed
        self._passed = passed
        self._broken = broken
        self._skipped = skipped
        self._warns = warnings
        self._exec_time = exec_time
        self._status = status
        self._retcode = retcode
        self._stdout = stdout

    def __repr__(self) -> str:
        return (
            f"test: '{self._test}', "
            f"failed: '{self._failed}', "
            f"passed: {self._passed}, "
            f"broken: {self._broken}, "
            f"skipped: {self._skipped}, "
            f"warnins: {self._warns}, "
            f"exec_time: {self._exec_time}, "
            f"status: {self._status}, "
            f"retcode: {self._retcode}, "
            f"stdout: {repr(self._stdout)}"
        )

    @property
    def test(self) -> Test:
        """
        :return: Test object.
        :rtype: Test
        """
        return self._test

    @property
    def return_code(self) -> int:
        """
        :return: Return code after execution.
        :rtype: int
        """
        return self._retcode

    @property
    def stdout(self) -> str:
        """
        :return: Test process stdout.
        :rtype: str
        """
        return self._stdout

    @property
    def status(self) -> int:
        """
        :return: Test result status.
        :rtype: int
        """
        return self._status

    @property
    def exec_time(self) -> float:
        return self._exec_time

    @property
    def failed(self) -> int:
        return self._failed

    @property
    def passed(self) -> int:
        return self._passed

    @property
    def broken(self) -> int:
        return self._broken

    @property
    def skipped(self) -> int:
        return self._skipped

    @property
    def warnings(self) -> int:
        return self._warns


class SuiteResults(Results):
    """
    Testing suite results definition.
    """

    def __init__(
        self,
        suite: Suite,
        tests: Optional[List[TestResults]] = None,
        distro: Optional[str] = None,
        distro_ver: Optional[str] = None,
        kernel: Optional[str] = None,
        cmdline: Optional[str] = None,
        arch: Optional[str] = None,
        cpu: Optional[str] = None,
        swap: Optional[str] = None,
        ram: Optional[str] = None,
    ) -> None:
        """
        :param suite: Test object declaration.
        :type suite: Suite
        :param tests: List of the tests results.
        :type tests: list(TestResults)
        :param distro: Distribution name.
        :type distro: str
        :param distro_ver: Distribution version.
        :type distro_ver: str
        :param kernel: Kernel version.
        :type kernel: str
        :param cmdline: /proc/cmdline.
        :type cmdline: str
        :param arch: OS architecture.
        :type arch: str
        :param cpu: CPU type info.
        :type cpu: str
        :param swap: Swap memory info.
        :type swap: str
        :param ram: RAM info.
        :type ram: str
        """
        if not suite:
            raise ValueError("Empty suite object")

        self._suite = suite
        self._tests = tests if tests is not None else []
        self._distro = distro
        self._distro_ver = distro_ver
        self._kernel = kernel
        self._cmdline = cmdline
        self._arch = arch
        self._cpu = cpu
        self._swap = swap
        self._ram = ram

    def __repr__(self) -> str:
        return (
            f"suite: '{self._suite}', "
            f"tests: '{self._tests}', "
            f"distro: {self._distro}, "
            f"distro_ver: {self._distro_ver}, "
            f"kernel: {self._kernel}, "
            f"cmdline: {self._cmdline}, "
            f"arch: {self._arch}, "
            f"cpu: {self._cpu}, "
            f"swap: {self._swap}, "
            f"ram: {self._ram}"
        )

    @property
    def suite(self) -> Suite:
        """
        :returns: Testing suite.
        :rtype: Suite
        """
        return self._suite

    @property
    def tests_results(self) -> List[TestResults]:
        """
        :returns: list of all tests results.
        :rtype: list(TestResults)
        """
        return self._tests

    def _get_result(self, attr: str) -> int:
        """
        Return the total number of results.
        """
        res = 0
        for test in self._tests:
            res += getattr(test, attr)

        return res

    @property
    def distro(self) -> Optional[str]:
        """
        :return: Linux distribution name.
        :rtype: str | None
        """
        return self._distro

    @property
    def distro_ver(self) -> Optional[str]:
        """
        :return: Linux distribution version.
        :rtype: str | None
        """
        return self._distro_ver

    @property
    def kernel(self) -> Optional[str]:
        """
        :return: Kernel version.
        :rtype: str | None
        """
        return self._kernel

    @property
    def cmdline(self) -> Optional[str]:
        """
        :return: /proc/cmdline.
        :rtype: str | None
        """
        return self._cmdline

    @property
    def arch(self) -> Optional[str]:
        """
        :return: Operating system architecture.
        :rtype: str | None
        """
        return self._arch

    @property
    def cpu(self) -> Optional[str]:
        """
        :return: Current CPU type.
        :rtype: str | None
        """
        return self._cpu

    @property
    def swap(self) -> Optional[str]:
        """
        :return: Current swap memory occupation.
        :rtype: str | None
        """
        return self._swap

    @property
    def ram(self) -> Optional[str]:
        """
        :return: Current RAM occupation.
        :rtype: str | None
        """
        return self._ram

    @property
    def exec_time(self) -> float:
        return self._get_result("exec_time")

    @property
    def failed(self) -> int:
        return self._get_result("failed")

    @property
    def passed(self) -> int:
        return self._get_result("passed")

    @property
    def broken(self) -> int:
        return self._get_result("broken")

    @property
    def skipped(self) -> int:
        return self._get_result("skipped")

    @property
    def warnings(self) -> int:
        return self._get_result("warnings")
