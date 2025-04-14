"""
.. module:: runner
    :platform: Linux
    :synopsis: module containing Runner definition and implementation.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import sys
import time
import asyncio
import logging
import libkirk
import libkirk.data
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.sut import IOBuffer
from libkirk.sut import KernelPanicError
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import TestResults
from libkirk.results import SuiteResults


class KernelTaintedError(KirkException):
    """
    Raised when kernel is tainted.
    """


class KernelTimeoutError(KirkException):
    """
    Raised when kernel is not replying anymore.
    """


class Scheduler:
    """
    Schedule jobs to run on target.
    """

    @property
    def results(self) -> list:
        """
        Current results. It's reset before every `schedule` call and
        it's populated when a job completes the execution.
        :returns: list(Results)
        """
        raise NotImplementedError()

    @property
    def stopped(self) -> bool:
        """
        Returns True when scheduler has been stopped.
        """
        raise NotImplementedError()

    async def stop(self) -> None:
        """
        Stop all running jobs.
        """
        raise NotImplementedError()

    async def schedule(self, jobs: list) -> None:
        """
        Schedule and execute a list of jobs.
        :param jobs: object containing jobs definition
        :type jobs: list(object)
        """
        raise NotImplementedError()


class RedirectTestStdout(IOBuffer):
    """
    Redirect test stdout data to UI events and save it.
    """

    def __init__(self, test: Test) -> None:
        self.stdout = ""
        self._test = test

    async def write(self, data: str) -> None:
        await libkirk.events.fire("test_stdout", self._test, data)
        self.stdout += data


class RedirectSUTStdout(IOBuffer):
    """
    Redirect SUT stdout data to UI events.
    """

    def __init__(self, sut: SUT) -> None:
        self._sut = sut

    async def write(self, data: str) -> None:
        await libkirk.events.fire("sut_stdout", self._sut.name, data)


class TestScheduler(Scheduler):
    """
    Schedule and run tests, taking into account status of the kernel
    during their execution, as well as tests timeout.
    """
    STATUS_OK = 0
    TEST_TIMEOUT = 1
    KERNEL_PANIC = 2
    KERNEL_TAINTED = 3
    KERNEL_TIMEOUT = 4

    def __init__(self, **kwargs: dict) -> None:
        """
        :param sut: object to communicate with SUT
        :type sut: SUT
        :param framework: framework handler
        :type framework: Framework
        :param timeout: timeout for tests execution
        :type timeout: float
        :param max_workers: maximum number of workers to schedule jobs
        :type max_workers: int
        :param force_parallel: Force parallel execution of all tests
        :type force_parallel: bool
        """
        self._logger = logging.getLogger("kirk.test_scheduler")
        self._sut = kwargs.get("sut", None)
        self._framework = kwargs.get("framework", None)
        self._timeout = max(kwargs.get("timeout", 3600.0), 0.0)
        self._max_workers = kwargs.get("max_workers", 1)
        self._force_parallel = kwargs.get("force_parallel", False)
        self._results = []
        self._stop = False
        self._stopped = False
        self._running_tests_sem = asyncio.Semaphore(1)
        self._schedule_lock = asyncio.Lock()

        if not self._sut:
            raise ValueError("SUT object is empty")

        if not self._framework:
            raise ValueError("Framework object is empty")

    async def _get_tainted_status(self) -> tuple:
        """
        Check tainted status of the Kernel.
        """
        code, messages = await self._sut.get_tainted_info()

        for msg in messages:
            if msg:
                self._logger.debug("Kernel tainted (%d): %s", code, msg)
                await libkirk.events.fire("kernel_tainted", msg)

        return code, messages

    async def _write_kmsg(self, test: Test) -> None:
        """
        If root, we write test information on /dev/kmsg.
        """
        self._logger.info("Writing test information on /dev/kmsg")

        ret = await self._sut.run_command("id -u")
        if ret["stdout"] != "0\n":
            self._logger.info("Can't write on /dev/kmsg from user")
            return

        message = f'{sys.argv[0]}[{os.getpid()}]: ' \
            f'starting test {test.name} ({test.full_command})\n'

        await self._sut.run_command(f'echo -n "{message}" > /dev/kmsg')

    @property
    def results(self) -> list:
        return self._results

    @property
    def stopped(self) -> bool:
        return self._stopped

    async def stop(self) -> None:
        self._logger.info("Stopping tests execution")
        self._stop = True

        try:
            # we enter in the semaphore queue in order to get highest
            # priority in the tests queue and wait for the running tests
            # to be completed
            async with self._running_tests_sem:
                pass

            self._logger.info("Wait for running tests to be completed")

            async with self._schedule_lock:
                pass
        finally:
            self._stop = False
            self._stopped = True

        self._logger.info("All tests have been completed")

    # pylint: disable=too-many-statements
    # pylint: disable=too-many-locals
    async def _run_test(self, test: Test) -> None:
        """
        Run a single test and populate the results array.
        """
        async with self._running_tests_sem:
            if self._stop:
                self._logger.info("Test '%s' has been stopped", test.name)
                return None

            self._logger.info("Running test %s", test.name)
            self._logger.debug(test)

            await libkirk.events.fire("test_started", test)
            await self._write_kmsg(test)

            iobuffer = RedirectTestStdout(test)
            cmd = test.full_command
            start_t = time.time()
            exec_time = 0
            test_data = None
            tainted_msg = None
            status = self.STATUS_OK

            try:
                tainted_code1, _ = await self._get_tainted_status()

                test_data = await asyncio.wait_for(self._sut.run_command(
                    cmd,
                    cwd=test.cwd,
                    env=test.env,
                    iobuffer=iobuffer),
                    timeout=self._timeout
                )

                tainted_code2, tainted_msg2 = await self._get_tainted_status()
                if tainted_code2 != tainted_code1:
                    self._logger.info(
                        "Recognised Kernel tainted: %s",
                        tainted_msg2)

                    tainted_msg = tainted_msg2
                    status = self.KERNEL_TAINTED
            except libkirk.sut.KernelPanicError:
                exec_time = time.time() - start_t

                self._logger.info("Recognised Kernel panic")
                status = self.KERNEL_PANIC
            except asyncio.TimeoutError:
                exec_time = time.time() - start_t
                status = self.TEST_TIMEOUT

                self._logger.info(
                    "Got test timeout. "
                    "Checking if SUT is still replying")

                try:
                    await asyncio.wait_for(
                        self._sut.ping(),
                        timeout=10
                    )

                    self._logger.info("SUT replied")
                except asyncio.TimeoutError:
                    status = self.KERNEL_TIMEOUT

            # create test results and save it
            if status not in [self.STATUS_OK, self.KERNEL_TAINTED]:
                test_data = {
                    "name": test.name,
                    "command": test.full_command,
                    "stdout": iobuffer.stdout,
                    "returncode": -1,
                    "exec_time": exec_time,
                }

            results = await self._framework.read_result(
                test,
                test_data["stdout"],
                test_data["returncode"],
                test_data["exec_time"])

            self._logger.debug("results=%s", results)
            self._results.append(results)

            # raise kernel errors at the end so we can collect test results
            if status == self.KERNEL_TAINTED:
                await libkirk.events.fire("kernel_tainted", tainted_msg)
                raise KernelTaintedError()

            if status == self.KERNEL_PANIC:
                await libkirk.events.fire("kernel_panic")
                raise KernelPanicError()

            if status == self.KERNEL_TIMEOUT:
                await libkirk.events.fire("sut_not_responding")
                raise KernelTimeoutError()

            await libkirk.events.fire("test_completed", results)

            self._logger.info("Test completed: %s", test.name)
            self._logger.debug(results)

    async def _run_and_wait(self, tests: list) -> None:
        """
        Run tests one after another.
        """
        if not tests:
            return

        self._logger.info("Scheduling %d tests on single worker", len(tests))

        self._running_tests_sem = asyncio.Semaphore(1)

        for test in tests:
            await self._run_test(test)

    async def _run_parallel(self, tests: list) -> None:
        """
        Run tests in parallel.
        """
        if not tests:
            return

        self._running_tests_sem = asyncio.Semaphore(self._max_workers)
        coros = [self._run_test(test) for test in tests]

        self._logger.info(
            "Scheduling %d tests on %d workers",
            len(coros),
            self._max_workers)

        await asyncio.gather(*coros)

    async def schedule(self, jobs: list) -> None:
        if not jobs:
            raise ValueError("jobs list is empty")

        for job in jobs:
            if not isinstance(job, Test):
                raise ValueError("jobs must be a list of Test")

        async with self._schedule_lock:
            self._logger.info("Check what tests can be run in parallel")

            self._results.clear()

            try:
                if self._force_parallel:
                    await self._run_parallel(jobs)
                else:
                    if self._max_workers > 1:
                        await self._run_parallel([
                            test for test in jobs if test.parallelizable
                        ])
                        await self._run_and_wait([
                            test for test in jobs if not test.parallelizable
                        ])
                    else:
                        await self._run_and_wait(jobs)
            except KirkException as err:
                exc_name = err.__class__.__name__
                self._logger.info("%s caught during tests execution", exc_name)

                raise_exc = not self._stop
                async with self._running_tests_sem:
                    pass

                if raise_exc:
                    self._logger.info("Propagating %s exception", exc_name)
                    raise err


class SuiteScheduler(Scheduler):
    """
    The Scheduler class implementation for suites execution.
    This is a special scheduler that schedules suites tests, checking for
    kernel status and rebooting SUT if we have some issues with it
    (i.e. kernel panic).
    """

    def __init__(self, **kwargs: dict) -> None:
        """
        :param sut: object used to communicate with SUT
        :type sut: SUT
        :param framework: framework handler
        :type framework: Framework
        :param suite_timeout: timeout before stopping testing suite
        :type suite_timeout: float
        :param exec_timeout: timeout before stopping single execution
        :type exec_timeout: float
        :param max_workers: maximum number of workers to schedule jobs
        :type max_workers: int
        :param force_parallel: Force parallel execution of all tests
        :type force_parallel: bool
        """
        self._logger = logging.getLogger("kirk.suite_scheduler")
        self._sut = kwargs.get("sut", None)
        self._framework = kwargs.get("framework", None)
        self._suite_timeout = max(kwargs.get("suite_timeout", 3600.0), 0.0)
        self._results = []
        self._stop = False
        self._stopped = False
        self._schedule_lock = asyncio.Lock()
        self._reboot_lock = asyncio.Lock()
        self._sut_rebooted = False

        if not self._sut:
            raise ValueError("SUT is an empty object")

        if not self._framework:
            raise ValueError("Framework object is empty")

        force_parallel = kwargs.get("force_parallel", False)
        exec_timeout = max(kwargs.get("exec_timeout", 3600.0), 0.0)

        self._scheduler = TestScheduler(
            sut=self._sut,
            framework=self._framework,
            timeout=exec_timeout,
            max_workers=kwargs.get("max_workers", 1),
            force_parallel=force_parallel)

    @property
    def results(self) -> list:
        return self._results

    @property
    def stopped(self) -> bool:
        return self._stopped

    async def stop(self) -> None:
        self._logger.info("Stopping suites execution")

        self._stop = True
        try:
            await self._scheduler.stop()

            async with self._schedule_lock:
                pass
        finally:
            self._stop = False
            self._stopped = True

        self._logger.info("Suites execution has stopped")

    async def _restart_sut(self) -> None:
        """
        Reboot the SUT.
        """
        async with self._reboot_lock:
            self._logger.info("Rebooting SUT")

            await libkirk.events.fire("sut_restart", self._sut.name)

            iobuffer = RedirectSUTStdout(self._sut)

            await self._scheduler.stop()
            await self._sut.stop(iobuffer=iobuffer)
            await self._sut.ensure_communicate(iobuffer=iobuffer)

            self._logger.info("SUT rebooted")

    async def _run_suite(self, suite: Suite) -> None:
        """
        Run a single testing suite and populate the results array.
        """
        self._logger.info("Running suite %s", suite.name)
        self._logger.debug(suite)

        await libkirk.events.fire("suite_started", suite)

        info = await self._sut.get_info()

        timed_out = False
        exec_times = []
        tests_results = []
        tests_left = list(suite.tests)
        reboot_event = asyncio.Event()

        try:
            while not self._stop and tests_left:
                try:
                    start_t = time.time()
                    await asyncio.wait_for(
                        self._scheduler.schedule(tests_left),
                        timeout=self._suite_timeout
                    )
                    exec_times.append(time.time() - start_t)
                except asyncio.TimeoutError:
                    self._logger.info(
                        "Testing suite timed out: %s", suite.name)

                    await libkirk.events.fire(
                        "suite_timeout",
                        suite,
                        self._suite_timeout)

                    timed_out = True
                except (KernelPanicError,
                        KernelTaintedError,
                        KernelTimeoutError):
                    if self._reboot_lock.locked():
                        self._logger.info("SUT is rebooting. Waiting...")
                        await reboot_event.wait()
                    else:
                        await self._restart_sut()
                        reboot_event.set()
                finally:
                    tests_results.extend(self._scheduler.results)

                # tests_left array will be populated when SUT is
                # rebooted after a kernel error
                tests_left.clear()

                for test in suite.tests:
                    found = False
                    for test_res in tests_results:
                        if test.name == test_res.test.name:
                            found = True
                            break

                    if not found:
                        tests_left.append(test)

                if timed_out:
                    for test in tests_left:
                        tests_results.append(
                            TestResults(
                                test=test,
                                failed=0,
                                passed=0,
                                broken=0,
                                skipped=1,
                                warnings=0,
                                exec_time=0.0,
                                retcode=32,
                                stdout=""
                            )
                        )

                    # no more tests need to be run
                    tests_left.clear()
                    break
        finally:
            suite_exec_time = sum(exec_times)
            if not exec_times:
                suite_exec_time = self._suite_timeout

            suite_results = SuiteResults(
                suite=suite,
                tests=tests_results,
                distro=info["distro"],
                distro_ver=info["distro_ver"],
                kernel=info["kernel"],
                arch=info["arch"],
                cpu=info["cpu"],
                swap=info["swap"],
                ram=info["ram"])

            await libkirk.events.fire(
                "suite_completed",
                suite_results,
                suite_exec_time)

            self._logger.info("Suite completed")
            self._logger.debug(suite_results)

            self._results.append(suite_results)

    async def schedule(self, jobs: list) -> None:
        if not jobs:
            raise ValueError("jobs list is empty")

        for job in jobs:
            if not isinstance(job, Suite):
                raise ValueError("jobs must be a list of Suite")

        async with self._schedule_lock:
            self._results.clear()

            for suite in jobs:
                await self._run_suite(suite)
