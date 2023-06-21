"""
.. module:: data
    :platform: Linux
    :synopsis: module containing suites data definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
from libkirk.data import Test
from libkirk.data import Suite


class ResultStatus:
    """
    Overall status of the test. This is a specific flag that is used to
    recognize final test status. For example, we might have 10 tests passing
    inside a single test binary, but the overall status of the test is fine, so
    we assign a PASS status.
    """
    # regular test run
    PASS = 0

    # test broken result
    BROK = 2

    # test warns
    WARN = 4

    # test failure
    FAIL = 16

    # test configuration error
    CONF = 32


class Results:
    """
    Base class for results.
    """

    @property
    def exec_time(self) -> float:
        """
        Execution time.
        :returns: float
        """
        raise NotImplementedError()

    @property
    def failed(self) -> int:
        """
        Number of TFAIL.
        :returns: int
        """
        raise NotImplementedError()

    @property
    def passed(self) -> int:
        """
        Number of TPASS.
        :returns: int
        """
        raise NotImplementedError()

    @property
    def broken(self) -> int:
        """
        Number of TBROK.
        :returns: int
        """
        raise NotImplementedError()

    @property
    def skipped(self) -> int:
        """
        Number of TSKIP.
        :returns: int
        """
        raise NotImplementedError()

    @property
    def warnings(self) -> int:
        """
        Number of TWARN.
        :returns: int
        """
        raise NotImplementedError()


class TestResults(Results):
    """
    Test results definition.
    """

    def __init__(self, **kwargs) -> None:
        """
        :param test: Test object declaration
        :type test: Test
        :param failed: number of TFAIL
        :type failed: int
        :param passed: number of TPASS
        :type passed: int
        :param broken: number of TBROK
        :type broken: int
        :param skipped: number of TSKIP
        :type skipped: int
        :param warnings: number of TWARN
        :type warnings: int
        :param exec_time: time for test's execution
        :type exec_time: float
        :param status: overall status of the test
        :type status: int
        :param retcode: return code of the executed test
        :type retcode: int
        :param stdout: stdout of the test
        :type stdout: str
        """
        self._test = kwargs.get("test", None)
        self._failed = max(kwargs.get("failed", 0), 0)
        self._passed = max(kwargs.get("passed", 0), 0)
        self._broken = max(kwargs.get("broken", 0), 0)
        self._skipped = max(kwargs.get("skipped", 0), 0)
        self._warns = max(kwargs.get("warnings", 0), 0)
        self._exec_t = max(kwargs.get("exec_time", 0.0), 0.0)
        self._retcode = kwargs.get("retcode", 0)
        self._status = kwargs.get("status", ResultStatus.PASS)
        self._stdout = kwargs.get("stdout", None)

        if not self._test:
            raise ValueError("Empty test object")

    def __repr__(self) -> str:
        return \
            f"test: '{self._test}', " \
            f"failed: '{self._failed}', " \
            f"passed: {self._passed}, " \
            f"broken: {self._broken}, " \
            f"skipped: {self._skipped}, " \
            f"warnins: {self._warns}, " \
            f"status: {self._status}, " \
            f"exec_time: {self._exec_t}, " \
            f"retcode: {self._retcode}, " \
            f"stdout: {repr(self._stdout)}"

    @property
    def test(self) -> Test:
        """
        Test object declaration.
        :returns: Test
        """
        return self._test

    @property
    def return_code(self) -> int:
        """
        Return code after execution.
        :returns: int
        """
        return self._retcode

    @property
    def stdout(self) -> str:
        """
        Return the ending stdout.
        :returns: str
        """
        return self._stdout

    @property
    def status(self) -> int:
        """
        Overall test result status.
        :returns: int
        """
        return self._status

    @property
    def exec_time(self) -> float:
        return self._exec_t

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

    def __init__(self, **kwargs) -> None:
        """
        :param suite: Test object declaration
        :type suite: Suite
        :param tests: List of the tests results
        :type tests: list(TestResults)
        :param distro: distribution name
        :type distro: str
        :param distro_ver: distribution version
        :type distro_ver: str
        :param kernel: kernel version
        :type kernel: str
        :param arch: OS architecture
        :type arch: str
        """
        self._suite = kwargs.get("suite", None)
        self._tests = kwargs.get("tests", [])
        self._distro = kwargs.get("distro", None)
        self._distro_ver = kwargs.get("distro_ver", None)
        self._kernel = kwargs.get("kernel", None)
        self._arch = kwargs.get("arch", None)
        self._cpu = kwargs.get("cpu", None)
        self._swap = kwargs.get("swap", None)
        self._ram = kwargs.get("ram", None)

        if not self._suite:
            raise ValueError("Empty suite object")

    def __repr__(self) -> str:
        return \
            f"suite: '{self._suite}', " \
            f"tests: '{self._tests}', " \
            f"distro: {self._distro}, " \
            f"distro_ver: {self._distro_ver}, " \
            f"kernel: {self._kernel}, " \
            f"arch: {self._arch}, " \
            f"cpu: {self._cpu}, " \
            f"swap: {self._swap}, " \
            f"ram: {self._ram}"

    @property
    def suite(self) -> Suite:
        """
        Suite object declaration.
        :returns: Suite
        """
        return self._suite

    @property
    def tests_results(self) -> list:
        """
        Results of all tests.
        :returns: list(TestResults)
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
    def distro(self) -> str:
        """
        Distribution name.
        """
        return self._distro

    @property
    def distro_ver(self) -> str:
        """
        Distribution version.
        """
        return self._distro_ver

    @property
    def kernel(self) -> str:
        """
        Kernel version.
        """
        return self._kernel

    @property
    def arch(self) -> str:
        """
        Operating system architecture.
        """
        return self._arch

    @property
    def cpu(self) -> str:
        """
        Current CPU type.
        """
        return self._cpu

    @property
    def swap(self) -> str:
        """
        Current swap memory occupation.
        """
        return self._swap

    @property
    def ram(self) -> str:
        """
        Current RAM occupation.
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
