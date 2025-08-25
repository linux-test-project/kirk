"""
.. module:: session
    :platform: Linux
    :synopsis: session declaration

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import copy
import logging
import os
import random
import re
from typing import Dict, List, Optional

import libkirk
import libkirk.types
from libkirk.data import Suite
from libkirk.errors import KirkException
from libkirk.export import JSONExporter
from libkirk.io import AsyncFile
from libkirk.results import TestResults
from libkirk.scheduler import SuiteScheduler
from libkirk.sut import SUT, IOBuffer


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
        """
        self._logger = logging.getLogger("kirk.session")
        self._tmpdir = kwargs.get("tmpdir", None)
        self._framework = kwargs.get("framework", None)
        self._sut = kwargs.get("sut", None)
        self._exec_timeout = kwargs.get("exec_timeout", 3600.0)
        self._force_parallel = kwargs.get("force_parallel", False)
        self._stop = False
        self._exec_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()
        self._results = []

        if not self._tmpdir:
            raise ValueError("tmpdir is empty")

        if not self._framework:
            raise ValueError("framework is empty")

        if not self._sut:
            raise ValueError("sut is empty")

        suite_timeout = kwargs.get("suite_timeout", 3600.0)
        workers = kwargs.get("workers", 1)

        self._scheduler = SuiteScheduler(
            sut=self._sut,
            framework=self._framework,
            suite_timeout=suite_timeout,
            exec_timeout=self._exec_timeout,
            max_workers=workers,
        )

        self._curr_suite = ""
        self._setup_debug_log()
        self._setup_test_save()

        if not self._sut.parallel_execution:
            self._logger.info(
                "SUT doesn't support parallel execution. Forcing workers=1."
            )
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
            "%(asctime)s - %(name)s:%(lineno)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def _setup_test_save(self) -> None:
        """
        Setup event for complete test saving.
        """
        if not self._tmpdir.abspath:
            return

        async def save_suite_started(suite: Suite) -> None:
            self._curr_suite = suite.name

        async def save_test_file(results: TestResults) -> None:
            epath = os.path.join(self._tmpdir.abspath, "executed")
            async with AsyncFile(epath, "a+") as efile:
                await efile.write(f"{self._curr_suite}::{results.test.name}\n")

        libkirk.events.register("suite_started", save_suite_started)
        libkirk.events.register("test_completed", save_test_file)

    async def _read_restored_session(self, path: str) -> Dict[str, List[str]]:
        """
        Read restored session.
        """
        data = {}
        if not (path and os.path.exists(path)):
            return data

        epath = os.path.join(path, "executed")
        if not os.path.exists(epath):
            return data

        self._logger.info("Reading previous executed tests")

        async with AsyncFile(epath, "r") as efile:
            async for line in efile:
                if not line:
                    continue

                suite, test = line.split("::")
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
        await self._sut.ensure_communicate(iobuffer=RedirectSUTStdout(self._sut, False))

    async def _stop_sut(self) -> None:
        """
        Stop the SUT.
        """
        if not await self._sut.is_running:
            return

        await libkirk.events.fire("sut_stop", self._sut.name)
        await self._sut.stop(iobuffer=RedirectSUTStdout(self._sut, False))

    async def _get_suites_objects(self, names: List[str]) -> List[Suite]:
        """
        Return suites objects by giving their names.
        """
        coros = []
        for suite in names:
            coros.append(self._framework.find_suite(self._sut, suite))

        if not coros:
            raise KirkException(f"Can't find suites: {names}")

        results = await asyncio.gather(*coros, return_exceptions=True)
        for suite in results:
            if isinstance(suite, Exception):
                raise suite

            if not suite:
                raise KirkException("Can't find suite objects")

        # pyrefly: ignore=no-matching-overload
        return list(results)

    async def _restore_tests(
        self, suites_obj: list, restore_path: Optional[str] = None
    ) -> None:
        """
        Remove all tests but the one which need to be restored.
        """
        if not restore_path:
            return

        restored = await self._read_restored_session(restore_path)
        if not restored:
            return

        await libkirk.events.fire("session_restore", restore_path)

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

    @staticmethod
    def _filter_tests(
        suites_obj: List[Suite],
        regex: Optional[str] = None,
        when_matching: bool = False,
    ) -> None:
        """
        Filter tests according to `regex`, if `when_matching` is True.
        """
        if not regex:
            return

        matcher = re.compile(regex)

        for suite_obj in suites_obj:
            toremove = []

            for test in suite_obj.tests:
                match = matcher.search(test.name)
                if (not match and not when_matching) or match and when_matching:
                    toremove.append(test)

            for item in toremove:
                suite_obj.tests.remove(item)

    @staticmethod
    def _apply_iterate(suites_obj: List[Suite], suite_iterate: int) -> List[Suite]:
        """
        Return testing suites after applying iterate parameters.
        """
        if suite_iterate <= 1:
            return suites_obj

        suites_list = []
        for suite in suites_obj:
            for i in range(0, suite_iterate):
                obj = copy.deepcopy(suite)
                obj.name = f"{suite.name}[{i}]"
                suites_list.append(obj)

        return suites_list

    async def _read_suites(
        self,
        names: List[str],
        pattern: Optional[str] = None,
        skip_tests: Optional[str] = None,
        restore_path: Optional[str] = None,
    ) -> List[Suite]:
        """
        Read suites and return a list of Suite objects.
        """
        suites_obj = await self._get_suites_objects(names)

        await self._restore_tests(suites_obj, restore_path)

        self._filter_tests(suites_obj, pattern, False)
        self._filter_tests(suites_obj, skip_tests, True)

        num_tests = 0
        for suite_obj in suites_obj:
            num_tests += len(suite_obj.tests)

        if num_tests == 0:
            raise KirkException("No tests selected")

        if self._force_parallel:
            for suite in suites_obj:
                for test in suite.tests:
                    test.force_parallel()

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
                        iobuffer=RedirectSUTStdout(self._sut, True),
                    ),
                    timeout=self._exec_timeout,
                )

                await libkirk.events.fire(
                    "run_cmd_stop", command, ret["stdout"], ret["returncode"]
                )
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

    async def _schedule_once(self, suites_obj: List[Suite]) -> None:
        """
        Schedule tests only once.
        """
        await self._scheduler.schedule(suites_obj)
        self._results.extend(self._scheduler.results)

    async def _schedule_infinite(self, suites_obj: List[Suite]) -> None:
        """
        Schedule all testing suites infinite times.
        """
        suites_list = []
        suites_list.extend(suites_obj)

        count = 1
        while not self._stop:
            await self._schedule_once(suites_obj)
            if self._scheduler.stopped:
                break

            count += 1

            suites_list.clear()
            for suite in copy.deepcopy(suites_obj):
                suite.name = f"{suite.name}[{count}]"
                suites_list.append(suite)

    async def _run_scheduler(self, suites_obj: List[Suite], runtime: int) -> None:
        """
        Run the scheduler for specific amount of time given by `runtime`.
        """
        if runtime <= 0:
            await self._schedule_once(suites_obj)
            return

        try:
            await asyncio.wait_for(self._schedule_infinite(suites_obj), runtime)
        except asyncio.TimeoutError:
            await self._scheduler.stop()

    async def _apply_fault_injection(self, fault_prob) -> None:
        """
        Check if we can apply fault injection configuration
        and eventually does it.
        """
        warn_msg = ""

        if not await self._sut.logged_as_root():
            if fault_prob != 0:
                warn_msg = "Run as root to use kernel fault injection"
        else:
            if await self._sut.is_fault_injection_enabled():
                await self._sut.setup_fault_injection(fault_prob)
            else:
                if fault_prob != 0:
                    warn_msg = "Fault injection is not enabled. Running tests normally"

        if warn_msg:
            self._logger.info(warn_msg)
            await libkirk.events.fire("session_warning", warn_msg)

    async def run(
        self,
        command: Optional[str] = None,
        suites: Optional[List[str]] = None,
        pattern: Optional[str] = None,
        skip_tests: Optional[str] = None,
        report_path: Optional[str] = None,
        restore_path: Optional[str] = None,
        suite_iterate: int = 1,
        randomize: bool = False,
        runtime: int = 0,
        fault_prob: int = 0,
    ) -> None:
        """
        Run a new session and store results inside a JSON file.
        :param command: single command to run before suites
        :type command: str
        :param suites: list of suites to execute
        :type suites: list
        :param pattern: regex pattern to include tests
        :types pattern: str
        :param skip_tests: regex for tests to skip
        :types skip_tests: str
        :param report_path: JSON report path
        :type report_path: str
        :param restore_path: temporary directory generated by a previous session
        :type restore_path: str
        :param suite_iterate: execute all suites multiple times
        :type suite_iterate: int
        :param randomize: randomize all tests if True
        :type randomize: bool
        :param runtime: for how long we want to run the session
        :type runtime: int
        :param fault_prob: fault injection probability
        :type fault_prob: int
        """
        async with self._run_lock:
            await libkirk.events.fire("session_started", self._tmpdir.abspath)

            if not self._sut.parallel_execution:
                await libkirk.events.fire(
                    "session_warning", "SUT doesn't support parallel execution"
                )

            try:
                await self._start_sut()

                if command:
                    await self._exec_command(command)

                if fault_prob != 0:
                    await self._apply_fault_injection(fault_prob)

                if suites:
                    suites_obj = await self._read_suites(
                        suites, pattern, skip_tests, restore_path
                    )

                    suites_obj = self._apply_iterate(suites_obj, suite_iterate)

                    if randomize:
                        for suite in suites_obj:
                            random.shuffle(suite.tests)

                    await self._run_scheduler(suites_obj, runtime)
            except KirkException as err:
                if not self._stop:
                    self._logger.exception(err)
                    await libkirk.events.fire("session_error", str(err))
                    raise err
            finally:
                try:
                    # configure fault injection to the original values
                    if fault_prob != 0:
                        await self._apply_fault_injection(0)

                    if self._results:
                        exporter = JSONExporter()

                        tasks = []
                        tasks.append(
                            exporter.save_file(
                                self._results,
                                os.path.join(self._tmpdir.abspath, "results.json"),
                            )
                        )

                        if report_path:
                            tasks.append(exporter.save_file(self._results, report_path))

                        await asyncio.gather(*tasks)

                        await libkirk.events.fire(
                            "session_completed", self._scheduler.results
                        )
                except KirkException as err:
                    self._logger.exception(err)
                    await libkirk.events.fire("session_error", str(err))
                    raise err
                finally:
                    self._results.clear()
                    await self._inner_stop()
