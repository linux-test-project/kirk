"""
Unittests for runner module.
"""
import re
import time
import asyncio
import pytest
import kirk.data
from kirk.host import HostSUT
from kirk.scheduler import TestScheduler
from kirk.scheduler import SuiteScheduler
from kirk.scheduler import KernelTainedError
from kirk.scheduler import KernelTimeoutError
from kirk.scheduler import KernelPanicError

pytestmark = pytest.mark.asyncio


class MockHostSUT(HostSUT):
    """
    HostSUT mock.
    """

    async def get_info(self) -> dict:
        return {
            "distro": "openSUSE",
            "distro_ver": "15.3",
            "kernel": "5.10",
            "arch": "x86_64",
            "cpu": "x86_64",
            "swap": "0",
            "ram": "1M",
        }

    async def get_tainted_info(self) -> tuple:
        return 0, [""]


class MockTestScheduler(TestScheduler):
    """
    TestScheduler mock that is not checking for tainted kernel
    and it doesn't write into /dev/kmsg
    """

    async def _write_kmsg(self, test) -> None:
        pass


class MockSuiteScheduler(SuiteScheduler):
    """
    SuiteScheduler mock that traces SUT reboots.
    """

    def __init__(self, **kwargs: dict) -> None:
        super().__init__(**kwargs)
        self._scheduler = MockTestScheduler(
            sut=kwargs.get("sut", None),
            timeout=kwargs.get("exec_timeout", 3600),
            max_workers=kwargs.get("max_workers", 1)
        )
        self._rebooted = 0

    async def _restart_sut(self) -> None:
        self._logger.info("Rebooting the SUT")

        await self._scheduler.stop()
        await self._sut.stop()
        await self._sut.communicate()

        self._rebooted += 1

    @property
    def rebooted(self) -> int:
        return self._rebooted


@pytest.fixture
async def sut():
    """
    SUT object.
    """
    obj = MockHostSUT()
    obj.setup()
    await obj.communicate()
    yield obj
    await obj.stop()


def make_parallelizable(suite):
    """
    Make an entire suite parallel.
    """
    for test in suite.tests:
        test._parallelizable = True


class TestTestScheduler:
    """
    Tests for TestScheduler.
    """

    @pytest.fixture
    async def create_runner(self, sut):
        def _callback(
                timeout: float = 3600.0,
                max_workers: int = 1) -> TestScheduler:
            obj = MockTestScheduler(
                sut=sut,
                timeout=timeout,
                max_workers=max_workers)

            return obj

        yield _callback

    async def test_schedule(self, create_runner):
        """
        Test the schedule method.
        """
        tests_num = 10
        content = ""
        for i in range(tests_num):
            content += f"test{i} sleep 0.02; echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=1)

        # single worker
        start = time.time()
        await runner.schedule(suite.tests)
        end_single = time.time() - start

        assert len(runner.results) == tests_num

        # check completed tests
        matcher = re.compile(r"test(?P<number>\d+)")
        numbers = list(range(tests_num))

        for res in runner.results:
            assert res.passed == 1
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 0
            assert res.warnings == 0
            assert 0 < res.exec_time < 1
            assert res.return_code == 0
            assert res.stdout == "ciao\n"

            match = matcher.search(res.test.name)
            assert match is not None

            number = int(match.group("number"))
            numbers.remove(number)

        assert len(numbers) == 0

        # multiple workers
        runner = create_runner(max_workers=tests_num)

        start = time.time()
        await runner.schedule(suite.tests)
        end_multi = time.time() - start

        assert len(runner.results) == tests_num
        assert end_multi < end_single

    async def test_schedule_stop(self, create_runner):
        """
        Test the schedule method when stop is called.
        """
        tests_num = 10
        content = "test0 echo ciao\n"
        for i in range(1, tests_num):
            content += f"test{i} sleep 1\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=tests_num)

        async def stop():
            await asyncio.sleep(0.5)
            await runner.stop()

        await asyncio.gather(*[
            runner.schedule(suite.tests),
            stop()
        ])

        assert len(runner.results) == 1
        res = runner.results[0]

        assert res.test.name == "test0"
        assert res.passed == 1
        assert res.failed == 0
        assert res.broken == 0
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == 0
        assert res.stdout == "ciao\n"

    async def test_schedule_kernel_tainted(self, create_runner):
        """
        Test the schedule method when kernel is tainted.
        """
        tainted = []

        async def mock_tainted():
            if tainted:
                tainted.clear()
                return 1, ["proprietary module was loaded"]

            tainted.append(1)
            return 0, [""]

        runner = create_runner(max_workers=1)
        runner._get_tainted_status = mock_tainted

        content = ""
        for i in range(2):
            content += f"test{i} echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        with pytest.raises(KernelTainedError):
            await runner.schedule(suite.tests)

        assert len(runner.results) == 1
        res = runner.results[0]

        assert res.test.name == "test0"
        assert res.passed == 1
        assert res.failed == 0
        assert res.broken == 0
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == 0
        assert res.stdout == "ciao\n"

    async def test_schedule_kernel_panic(self, create_runner):
        """
        Test the schedule method on kernel panic. It runs some tests in
        parallel then it generates a Kernel panic, it verifies that only one
        test has been executed and it failed.
        """
        content = "test0 echo Kernel panic\n"
        content += "test1 echo ciao; sleep 3\n"
        content += "test2 echo ciao; sleep 3\n"
        content += "test3 echo ciao; sleep 3\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=10)

        with pytest.raises(KernelPanicError):
            await runner.schedule(suite.tests)

        assert len(runner.results) == 1
        res = runner.results[0]

        assert res.test.name == "test0"
        assert res.passed == 0
        assert res.failed == 0
        assert res.broken == 1
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == -1
        assert res.stdout == "Kernel panic\n"

    async def test_schedule_kernel_timeout(self, sut, create_runner):
        """
        Test the schedule method on kernel timeout.
        """
        async def kernel_timeout(command, iobuffer=None) -> dict:
            raise asyncio.TimeoutError()

        sut.run_command = kernel_timeout

        content = ""
        for i in range(2):
            content += f"test{i} echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=1)

        with pytest.raises(KernelTimeoutError):
            await runner.schedule(suite.tests)

        assert len(runner.results) == 1
        res = runner.results[0]

        assert res.passed == 0
        assert res.failed == 0
        assert res.broken == 1
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == -1
        assert res.stdout == ""

    async def test_schedule_test_timeout(self, create_runner):
        """
        Test the schedule method on test timeout.
        """
        content = "test0 echo ciao; sleep 2\n"
        content += "test1 echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(timeout=0.5, max_workers=2)

        await runner.schedule(suite.tests)

        assert len(runner.results) == 2

        assert runner.results[0].test.name == "test1"
        assert runner.results[0].passed == 1
        assert runner.results[0].failed == 0
        assert runner.results[0].broken == 0
        assert runner.results[0].skipped == 0
        assert runner.results[0].warnings == 0
        assert 0 < runner.results[0].exec_time < 1
        assert runner.results[0].return_code == 0
        assert runner.results[0].stdout == "ciao\n"

        assert runner.results[1].test.name == "test0"
        assert runner.results[1].passed == 0
        assert runner.results[1].failed == 0
        assert runner.results[1].broken == 1
        assert runner.results[1].skipped == 0
        assert runner.results[1].warnings == 0
        assert 0 < runner.results[1].exec_time < 2
        assert runner.results[1].return_code == -1
        assert runner.results[1].stdout == "ciao\n"


class TestSuiteScheduler:
    """
    Tests for SuiteScheduler.
    """

    @pytest.fixture
    async def create_runner(self, sut):
        def _callback(
                suite_timeout: float = 3600.0,
                exec_timeout: float = 3600.0,
                max_workers: int = 1) -> SuiteScheduler:
            obj = MockSuiteScheduler(
                sut=sut,
                suite_timeout=suite_timeout,
                exec_timeout=exec_timeout,
                max_workers=max_workers)

            return obj

        yield _callback

    async def test_schedule(self, create_runner):
        """
        Test the schedule method.
        """
        tests_num = 10
        content = ""
        for i in range(tests_num):
            content += f"test{i} sleep 0.02; echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        # single worker
        runner = create_runner(max_workers=1)

        start = time.time()
        await runner.schedule([suite])
        end_single = time.time() - start

        assert len(runner.results) == 1

        assert runner.results[0].suite.name == "suite"
        assert runner.results[0].distro is not None
        assert runner.results[0].distro_ver is not None
        assert runner.results[0].kernel is not None
        assert runner.results[0].arch is not None
        assert runner.results[0].cpu is not None
        assert runner.results[0].swap is not None
        assert runner.results[0].ram is not None
        assert runner.results[0].passed == 10
        assert runner.results[0].failed == 0
        assert runner.results[0].broken == 0
        assert runner.results[0].skipped == 0
        assert runner.results[0].warnings == 0
        assert 0 < runner.results[0].exec_time < 10

        # check completed tests
        matcher = re.compile(r"test(?P<number>\d+)")
        numbers = list(range(tests_num))

        for res in runner.results[0].tests_results:
            assert res.passed == 1
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 0
            assert res.warnings == 0
            assert 0 < res.exec_time < 1
            assert res.return_code == 0
            assert res.stdout == "ciao\n"

            match = matcher.search(res.test.name)
            assert match is not None

            number = int(match.group("number"))
            numbers.remove(number)

        assert len(numbers) == 0

        # multiple workers
        runner = create_runner(max_workers=tests_num)

        start = time.time()
        await runner.schedule([suite])
        end_multi = time.time() - start

        assert len(runner.results) == 1
        assert end_multi < end_single

    async def test_schedule_stop(self, create_runner):
        """
        Test the schedule method when stop is called.
        """
        tests_num = 10
        content = "test0 echo ciao\n"
        for i in range(1, tests_num):
            content += f"test{i} sleep 1\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=tests_num)

        async def stop():
            await asyncio.sleep(0.5)
            await runner.stop()

        await asyncio.gather(*[
            runner.schedule([suite]),
            stop()
        ])

        assert len(runner.results) == 1
        suite_res = runner.results[0]

        assert len(suite_res.tests_results) == 1
        res = suite_res.tests_results[0]

        assert res.test.name == "test0"
        assert res.passed == 1
        assert res.failed == 0
        assert res.broken == 0
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == 0
        assert res.stdout == "ciao\n"

    async def test_schedule_kernel_tainted(self, sut, create_runner):
        """
        Test the schedule method when kernel is tainted.
        """
        tainted = []

        async def mock_tainted():
            if tainted:
                tainted.clear()
                return 1, ["proprietary module was loaded"]

            tainted.append(1)
            return 0, []

        tests_num = 4
        content = ""
        for i in range(tests_num):
            content += f"test{i} echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        sut.get_tainted_info = mock_tainted
        runner = create_runner(max_workers=1)

        await runner.schedule([suite])

        assert runner.rebooted == tests_num
        assert len(runner.results) == 1
        assert len(runner.results[0].tests_results) == tests_num

        # check completed tests
        matcher = re.compile(r"test(?P<number>\d+)")
        numbers = list(range(tests_num))

        for res in runner.results[0].tests_results:
            assert res.passed == 1
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 0
            assert res.warnings == 0
            assert 0 < res.exec_time < 1
            assert res.return_code == 0
            assert res.stdout == "ciao\n"

            match = matcher.search(res.test.name)
            assert match is not None

            number = int(match.group("number"))
            numbers.remove(number)

        assert len(numbers) == 0

    @pytest.mark.parametrize("max_workers", [1, 10])
    async def test_schedule_kernel_panic(self, create_runner, max_workers):
        """
        Test the schedule method on kernel panic.
        """
        tests_num = 3

        content = "test0 echo Kernel panic\n"
        content += "test1 echo ciao; sleep 0.3\n"
        for i in range(2, tests_num):
            content += f"test{i} echo ciao; sleep 0.3\n"

        suite = await kirk.data.read_runtest("suite", content)
        runner = create_runner(max_workers=max_workers)

        await runner.schedule([suite])
        make_parallelizable(suite)

        assert runner.rebooted == 1
        assert len(runner.results) == 1
        assert len(runner.results[0].tests_results) == tests_num

        res = runner.results[0].tests_results[0]
        assert res.passed == 0
        assert res.failed == 0
        assert res.broken == 1
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == -1
        assert res.stdout == "Kernel panic\n"

        # check completed tests
        matcher = re.compile(r"test(?P<number>\d+)")
        numbers = list(range(1, tests_num))

        for res in runner.results[0].tests_results[1:]:
            assert res.passed == 1
            assert res.failed == 0
            assert res.broken == 0
            assert res.skipped == 0
            assert res.warnings == 0
            assert 0 < res.exec_time < 2
            assert res.return_code == 0
            assert res.stdout == "ciao\n"

            match = matcher.search(res.test.name)
            assert match is not None

            number = int(match.group("number"))
            numbers.remove(number)

        assert len(numbers) == 0

    @pytest.mark.parametrize("max_workers", [1, 10])
    async def test_schedule_kernel_timeout(
            self,
            sut,
            create_runner,
            max_workers):
        """
        Test the schedule method on kernel timeout.
        """
        async def kernel_timeout(command, iobuffer=None) -> dict:
            raise asyncio.TimeoutError()

        sut.run_command = kernel_timeout

        content = ""
        for i in range(max_workers):
            content += f"test{i} echo ciao\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(max_workers=max_workers)

        await runner.schedule([suite])

        assert runner.rebooted == 1
        assert len(runner.results) == 1
        assert len(runner.results[0].tests_results) == max_workers

        # check completed tests
        matcher = re.compile(r"test(?P<number>\d+)")
        numbers = list(range(max_workers))

        for res in runner.results[0].tests_results:
            assert res.passed == 0
            assert res.failed == 0
            assert res.broken == 1
            assert res.skipped == 0
            assert res.warnings == 0
            assert 0 < res.exec_time < 1
            assert res.return_code == -1
            assert res.stdout == ""

            match = matcher.search(res.test.name)
            assert match is not None

            number = int(match.group("number"))
            numbers.remove(number)

        assert len(numbers) == 0

    @pytest.mark.parametrize("max_workers", [1, 10])
    async def test_schedule_suite_timeout(self, create_runner, max_workers):
        """
        Test the schedule method on suite timeout.
        """
        content = "test0 echo ciao\n"
        content += "test1 echo ciao; sleep 2\n"

        suite = await kirk.data.read_runtest("suite", content)
        make_parallelizable(suite)

        runner = create_runner(suite_timeout=0.5, max_workers=max_workers)

        await runner.schedule([suite])

        assert len(runner.results) == 1
        res = runner.results[0].tests_results[0]
        assert res.test.name == "test0"
        assert res.passed == 1
        assert res.failed == 0
        assert res.broken == 0
        assert res.skipped == 0
        assert res.warnings == 0
        assert 0 < res.exec_time < 1
        assert res.return_code == 0
        assert res.stdout == "ciao\n"

        res = runner.results[0].tests_results[1]
        assert res.test.name == "test1"
        assert res.passed == 0
        assert res.failed == 0
        assert res.broken == 0
        assert res.skipped == 1
        assert res.warnings == 0
        assert res.exec_time == 0
        assert res.return_code == 32
        assert res.stdout == ""
