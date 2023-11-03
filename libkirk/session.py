"""
.. module:: session
    :platform: Linux
    :synopsis: session declaration

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import logging
import asyncio
import libkirk
import libkirk.data
import libkirk.events
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.sut import IOBuffer
from libkirk.results import TestResults
from libkirk.export import JSONExporter
from libkirk.scheduler import SuiteScheduler


class RedirectSUTStdout(IOBuffer):
    """
    Redirect stdout data to UI events.
    """

    def __init__(self, sut: SUT, is_cmd: bool) -> None:
        self._sut = sut
        self._is_cmd = is_cmd

    async def write(self, data: str) -> None:
        if self._is_cmd:
            await libkirk.events.fire("run_cmd_stdout", data)
        else:
            await libkirk.events.fire("sut_stdout", self._sut.name, data)


class Session:
    """
    The session runner.
    """

    def __init__(self, **kwargs) -> None:
        """
        :param tmpdir: temporary directory
        :type tmpdir: TempDir
        :param framework: testing framework we are using
        :type framework: Framework
        :param sut: SUT communication object
        :type sut: SUT
        :param exec_timeout: test timeout
        :type exec_timeout: float
        :param suite_timeout: testing suite timeout
        :type suite_timeout: float
        :param workers: number of workers for testing suite scheduler
        :type workers: int
        :param force_parallel: Force parallel execution of all tests
        :type force_parallel: bool
        :param skip_tests: regexp that exclude tests from execution
        :type skip_tests: str
        """
        self._logger = logging.getLogger("kirk.session")
        self._tmpdir = kwargs.get("tmpdir", None)
        self._framework = kwargs.get("framework", None)
        self._sut = kwargs.get("sut", None)
        self._exec_timeout = kwargs.get("exec_timeout", 3600.0)
        self._stop = False
        self._exec_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()

        if not self._tmpdir:
            raise ValueError("tmpdir is empty")

        if not self._framework:
            raise ValueError("framework is empty")

        if not self._sut:
            raise ValueError("sut is empty")

        suite_timeout = kwargs.get("suite_timeout", 3600.0)
        workers = kwargs.get("workers", 1)
        force_parallel = kwargs.get("force_parallel", False)
        skip_tests = kwargs.get("skip_tests", None)

        self._scheduler = SuiteScheduler(
            sut=self._sut,
            framework=self._framework,
            suite_timeout=suite_timeout,
            exec_timeout=self._exec_timeout,
            max_workers=workers,
            skip_tests=skip_tests,
            force_parallel=force_parallel)

        self._curr_suite = ''
        self._setup_debug_log()
        self._setup_test_save()

        if not self._sut.parallel_execution:
            self._logger.info(
                "SUT doesn't support parallel execution. "
                "Forcing workers=1.")
            self._workers = 1

    def _setup_debug_log(self) -> None:
        """
        Set logging module so we save a log file with debugging information
        inside the temporary path.
        """
        if not self._tmpdir.abspath:
            return

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        debug_file = os.path.join(self._tmpdir.abspath, "debug.log")
        handler = logging.FileHandler(debug_file, encoding="utf8")
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s:%(lineno)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def _setup_test_save(self) -> None:
        """
        Setup event for complete test saving.
        """
        if not self._tmpdir.abspath:
            return

        async def save_suite_started(suite: libkirk.data.Suite) -> None:
            self._curr_suite = suite.name

        async def save_test_file(results: TestResults) -> None:
            epath = os.path.join(self._tmpdir.abspath, 'executed')
            with open(epath, 'a+', encoding='utf-8') as efile:
                efile.write(f"{self._curr_suite}::{results.test.name}\n")

        libkirk.events.register("suite_started", save_suite_started)
        libkirk.events.register("test_completed", save_test_file)

    def _read_restored_session(self, path: str) -> dict:
        """
        Read restored session.
        """
        data = {}
        if not (path and os.path.exists(path)):
            return data

        epath = os.path.join(path, 'executed')
        if not os.path.exists(epath):
            return data

        self._logger.info("Reading previous executed tests")

        with open(epath, 'r', encoding='utf-8') as efile:
            for line in efile:
                suite, test = line.split('::')
                if not (suite and test):
                    continue

                if suite not in data:
                    data[suite] = []

                data[suite].append(test.rstrip())

        self._logger.debug(data)

        return data

    async def _start_sut(self) -> None:
        """
        Start communicating with SUT.
        """
        await libkirk.events.fire("sut_start", self._sut.name)
        await self._sut.ensure_communicate(
            iobuffer=RedirectSUTStdout(self._sut, False))

    async def _stop_sut(self) -> None:
        """
        Stop the SUT.
        """
        if not await self._sut.is_running:
            return

        await libkirk.events.fire("sut_stop", self._sut.name)
        await self._sut.stop(iobuffer=RedirectSUTStdout(self._sut, False))

    async def _read_suites(self, suites: list, restore: str) -> list:
        """
        Read suites and return a list of Suite objects.
        """
        coros = []
        for suite in suites:
            coros.append(self._framework.find_suite(self._sut, suite))

        if not coros:
            raise KirkException(f"Can't find suites: {suites}")

        suites_obj = await asyncio.gather(*coros, return_exceptions=True)
        for suite in suites_obj:
            if isinstance(suite, Exception):
                raise suite

            if not suite:
                raise KirkException("Can't find suite objects")

        restored = self._read_restored_session(restore)
        if restored:
            await libkirk.events.fire("session_restore", restore)

            for suite_obj in suites_obj:
                toremove = []
                suite = suite_obj.name
                if suite not in restored:
                    continue

                for test in suite_obj.tests:
                    if test.name in restored[suite]:
                        toremove.append(test)

                for test in toremove:
                    suite_obj.tests.remove(test)

                toremove.clear()

        return suites_obj

    async def _exec_command(self, command: str) -> None:
        """
        Execute a single command on SUT.
        """
        async with self._exec_lock:
            exc = None
            try:
                await libkirk.events.fire("run_cmd_start", command)

                test = await self._framework.find_command(self._sut, command)

                ret = await asyncio.wait_for(
                    self._sut.run_command(
                        test.full_command,
                        cwd=test.cwd,
                        env=test.env,
                        iobuffer=RedirectSUTStdout(self._sut, True)),
                    timeout=self._exec_timeout
                )

                await libkirk.events.fire(
                    "run_cmd_stop",
                    command,
                    ret["stdout"],
                    ret["returncode"])
            except asyncio.TimeoutError:
                exc = KirkException(f"Command timeout: {repr(command)}")
            except KirkException as err:
                if not self._stop:
                    exc = err

            if exc:
                raise exc

    async def _inner_stop(self) -> None:
        """
        Stop scheduler and SUT.
        """
        if self._scheduler:
            await self._scheduler.stop()

        await self._stop_sut()

    async def stop(self) -> None:
        """
        Stop the current session.
        """
        self._stop = True
        try:
            await self._inner_stop()

            async with self._run_lock:
                pass

            async with self._exec_lock:
                pass
        finally:
            await libkirk.events.fire("session_stopped")
            self._stop = False

    async def run(
            self,
            command: str = None,
            suites: list = None,
            report_path: str = None,
            restore: str = None) -> None:
        """
        Run a new session and store results inside a JSON file.
        :param command: single command to run before suites
        :type command: str
        :param suites: list of suites to execute
        :type suites: list
        :param report_path: JSON report path
        :type report_path: str
        :param restore: temporary directory generated by a previous session
        :type restore: str
        """
        async with self._run_lock:
            await libkirk.events.fire("session_started", self._tmpdir.abspath)

            if not self._sut.parallel_execution:
                await libkirk.events.fire(
                    "session_warning",
                    "SUT doesn't support parallel execution")

            try:
                await self._start_sut()

                if command:
                    await self._exec_command(command)

                if suites:
                    suites_obj = await self._read_suites(suites, restore)
                    await self._scheduler.schedule(suites_obj)
            except KirkException as err:
                if not self._stop:
                    self._logger.exception(err)
                    await libkirk.events.fire("session_error", str(err))
                    raise err
            finally:
                try:
                    if self._scheduler.results:
                        exporter = JSONExporter()

                        tasks = []
                        tasks.append(
                            exporter.save_file(
                                self._scheduler.results,
                                os.path.join(
                                    self._tmpdir.abspath,
                                    "results.json")
                            ))

                        if report_path:
                            tasks.append(
                                exporter.save_file(
                                    self._scheduler.results,
                                    report_path
                                ))

                        await asyncio.gather(*tasks)

                        await libkirk.events.fire(
                            "session_completed",
                            self._scheduler.results)
                except KirkException as err:
                    self._logger.exception(err)
                    await libkirk.events.fire("session_error", str(err))
                    raise err
                finally:
                    await self._inner_stop()
