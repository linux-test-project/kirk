"""
.. module:: session
    :platform: Linux
    :synopsis: session declaration

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import logging
import asyncio
import kirk
import kirk.data
import kirk.events
from kirk import KirkException
from kirk.sut import SUT
from kirk.sut import IOBuffer
from kirk.export import JSONExporter
from kirk.scheduler import SuiteScheduler


class RedirectSUTStdout(IOBuffer):
    """
    Redirect stdout data to UI events.
    """

    def __init__(self, sut: SUT, is_cmd: bool) -> None:
        self._sut = sut
        self._is_cmd = is_cmd

    async def write(self, data: str) -> None:
        if self._is_cmd:
            await kirk.events.fire("run_cmd_stdout", data)
        else:
            await kirk.events.fire("sut_stdout", self._sut.name, data)


class Session:
    """
    The session runner.
    """

    def __init__(self, **kwargs) -> None:
        """
        :param tmpdir: temporary directory
        :type tmpdir: TempDir
        :param frameworks: list of frameworks
        :type frameworks: list(Framework)
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
        self._frameworks = kwargs.get("frameworks", None)
        self._sut = kwargs.get("sut", None)
        self._exec_timeout = kwargs.get("exec_timeout", 3600.0)
        self._stop = False
        self._exec_lock = asyncio.Lock()
        self._run_lock = asyncio.Lock()

        if not self._tmpdir:
            raise ValueError("tmpdir is empty")

        if not self._frameworks:
            raise ValueError("frameworks is empty")

        if not self._sut:
            raise ValueError("sut is empty")

        self._suite_timeout = kwargs.get("suite_timeout", 3600.0)
        self._workers = kwargs.get("workers", 1)
        self._force_parallel = kwargs.get("force_parallel", False)
        self._scheduler = None

        self._setup_debug_log()

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

    async def _start_sut(self) -> None:
        """
        Start communicating with SUT.
        """
        await kirk.events.fire("sut_start", self._sut.name)
        await self._sut.ensure_communicate(
            iobuffer=RedirectSUTStdout(self._sut, False))

    async def _stop_sut(self) -> None:
        """
        Stop the SUT.
        """
        if not await self._sut.is_running:
            return

        await kirk.events.fire("sut_stop", self._sut.name)
        await self._sut.stop(iobuffer=RedirectSUTStdout(self._sut, False))

    async def _read_suites(self, request: dict) -> list:
        """
        Read all testing suites and return suites objects.
        """
        coros = []
        for fwname, suites in request.items():
            fwork = None
            for item in self._frameworks:
                if item.name == fwname:
                    fwork = item
                    break

            if fwork:
                for suite in suites:
                    coros.append(fwork.find_suite(self._sut, suite))

        if not coros:
            raise KirkException(
                f"Can't find frameworks for request: {request}")

        suites_obj = await asyncio.gather(*coros, return_exceptions=True)
        for suite in suites_obj:
            if not suite:
                raise KirkException("Can't find suite objects")

        return suites_obj

    async def _exec_command(self, command: str) -> None:
        """
        Execute a single command on SUT.
        """
        async with self._exec_lock:
            try:
                await kirk.events.fire("run_cmd_start", command)

                ret = await asyncio.wait_for(
                    self._sut.run_command(
                        command,
                        iobuffer=RedirectSUTStdout(self._sut, True)),
                    timeout=self._exec_timeout
                )

                await kirk.events.fire(
                    "run_cmd_stop",
                    command,
                    ret["stdout"],
                    ret["returncode"])
            except asyncio.TimeoutError:
                raise KirkException(f"Command timeout: {repr(command)}")
            except KirkException as err:
                if not self._stop:
                    raise err

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
            await kirk.events.fire("session_stopped")
            self._stop = False

    async def run(
            self,
            command: str = None,
            suites: dict = None,
            skip_tests: str = None,
            report_path: str = None) -> None:
        """
        Run a new session and store results inside a JSON file.
        :param command: single command to run before suites
        :type command: str
        :param suites: list of suites by framework
        :type suites: dict
        :param skip_tests: regexp that exclude tests from execution
        :type skip_tests: str
        :param report_path: JSON report path
        :type report_path: str
        """
        async with self._run_lock:
            await kirk.events.fire("session_started", self._tmpdir.abspath)

            self._scheduler = SuiteScheduler(
                sut=self._sut,
                suite_timeout=self._suite_timeout,
                exec_timeout=self._exec_timeout,
                max_workers=self._workers,
                skip_tests=skip_tests,
                force_parallel=self._force_parallel)

            try:
                await self._start_sut()

                if command:
                    await self._exec_command(command)

                if suites:
                    suites_obj = await self._read_suites(suites)
                    await self._scheduler.schedule(suites_obj)
            except asyncio.CancelledError:
                await kirk.events.fire("session_stopped")
            except KirkException as err:
                if not self._stop:
                    self._logger.exception(err)
                    await kirk.events.fire("session_error", str(err))
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

                        await kirk.events.fire(
                            "session_completed",
                            self._scheduler.results)
                except KirkException as err:
                    self._logger.exception(err)
                    await kirk.events.fire("session_error", str(err))
                    raise err
                finally:
                    await self._inner_stop()
