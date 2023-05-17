"""
.. module:: session
    :platform: Linux
    :synopsis: session declaration

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import json
import logging
import asyncio
import kirk
import kirk.data
import kirk.events
from kirk import KirkException
from kirk.sut import SUT
from kirk.sut import IOBuffer
from kirk.tempfile import TempDir
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
        :param tmpdir: temporary directory path
        :type tmpdir: str
        :param ltpdir: LTP directory path
        :type ltpdir: str
        :param sut: SUT communication object
        :type sut: SUT
        :param sut_config: SUT object configuration
        :type sut_config: dict
        :param no_colors: if True, it disables LTP tests colors
        :type no_colors: bool
        :param exec_timeout: test timeout
        :type exec_timeout: float
        :param suite_timeout: testing suite timeout
        :type suite_timeout: float
        :param skip_tests: regexp excluding tests from execution
        :type skip_tests: str
        :param workers: number of workers for testing suite scheduler
        :type workers: int
        :param env: SUT environment vairables to inject before execution
        :type env: dict
        :param force_parallel: Force parallel execution of all tests
        :type force_parallel: bool
        """
        self._logger = logging.getLogger("kirk.session")
        self._tmpdir = TempDir(kwargs.get("tmpdir", "/tmp"))
        self._ltpdir = kwargs.get("ltpdir", "/opt/ltp")
        self._sut = kwargs.get("sut", None)
        self._no_colors = kwargs.get("no_colors", False)
        self._exec_timeout = kwargs.get("exec_timeout", 3600.0)
        self._env = kwargs.get("env", None)

        suite_timeout = kwargs.get("suite_timeout", 3600.0)
        skip_tests = kwargs.get("skip_tests", "")
        workers = kwargs.get("workers", 1)
        force_parallel = kwargs.get("force_parallel", False)

        self._scheduler = SuiteScheduler(
            sut=self._sut,
            suite_timeout=suite_timeout,
            exec_timeout=self._exec_timeout,
            max_workers=workers,
            skip_tests=skip_tests,
            force_parallel=force_parallel)

        if not self._sut:
            raise ValueError("sut is empty")

        self._sut_config = self._get_sut_config(kwargs.get("sut_config", {}))
        self._setup_debug_log()

        if not self._sut.parallel_execution:
            self._logger.info(
                "SUT doesn't support parallel execution. "
                "Forcing workers=1.")
            self._workers = 1

        metadata_path = os.path.join(self._ltpdir, "metadata", "kirk.json")
        self._metadata_json = None
        if os.path.isfile(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as metadata:
                self._metadata_json = json.loads(metadata.read())

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

    def _get_sut_config(self, sut_config: dict) -> dict:
        """
        Create the SUT configuration. The dictionary is usually passed to the
        `setup` method of the SUT, in order to setup the environment before
        running tests.
        """
        testcases = os.path.join(self._ltpdir, "testcases", "bin")

        env = {}
        env["PATH"] = "/sbin:/usr/sbin:/usr/local/sbin:" + \
            f"/root/bin:/usr/local/bin:/usr/bin:/bin:{testcases}"
        env["LTPROOT"] = self._ltpdir
        env["TMPDIR"] = self._tmpdir.root if self._tmpdir.root else "/tmp"
        env["LTP_TIMEOUT_MUL"] = str((self._exec_timeout * 0.9) / 300.0)

        if self._no_colors:
            env["LTP_COLORIZE_OUTPUT"] = "0"
        else:
            env["LTP_COLORIZE_OUTPUT"] = "1"

        if self._env:
            for key, value in self._env.items():
                if key in env:
                    continue

                self._logger.info("Set environment variable %s=%s", key, value)
                env[key] = value

        config = sut_config.copy()
        config['env'] = env
        config['cwd'] = testcases
        config['tmpdir'] = self._tmpdir.abspath

        return config

    async def _start_sut(self) -> None:
        """
        Start communicating with SUT.
        """
        self._sut.setup(**self._sut_config)

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

    async def _download_suites(self, suites: list) -> list:
        """
        Download all testing suites and return suites objects list.
        """
        if not os.path.isdir(os.path.join(self._tmpdir.abspath, "runtest")):
            self._tmpdir.mkdir("runtest")

        async def _download(suite: str) -> None:
            """
            Download a single suite inside temporary folder.
            """
            target = os.path.join(self._ltpdir, "runtest", suite)

            await kirk.events.fire(
                "suite_download_started",
                suite,
                target)

            data = await self._sut.fetch_file(target)
            data_str = data.decode(encoding="utf-8", errors="ignore")

            self._tmpdir.mkfile(os.path.join("runtest", suite), data_str)

            await kirk.events.fire(
                "suite_download_completed",
                suite,
                target)

            suite = await kirk.data.read_runtest(
                suite,
                data_str,
                metadata=self._metadata_json)

            return suite

        suites_obj = await asyncio.gather(*[
            _download(suite)
            for suite in suites
        ])

        return suites_obj

    async def _exec_command(self, command: str) -> None:
        """
        Execute a single command on SUT.
        """
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

    async def stop(self) -> None:
        """
        Stop the current session.
        """
        await self._scheduler.stop()
        await self._stop_sut()

    async def run(
            self,
            command: str = None,
            suites: list = None,
            report_path: str = None) -> None:
        """
        Run a new session and store results inside a JSON file.
        :param command: single command to run before suites
        :type command: str
        :param suites: name of the testing suites to run
        :type suites: list(str)
        :param report_path: JSON report path
        :type report_path: str
        """
        await kirk.events.fire(
            "session_started",
            self._tmpdir.abspath)

        try:
            await self._start_sut()

            if command:
                await self._exec_command(command)

            if suites:
                suites = await self._download_suites(suites)
                await self._scheduler.schedule(suites)

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
        except asyncio.CancelledError:
            await kirk.events.fire("session_stopped")
        except KirkException as err:
            self._logger.exception(err)
            await kirk.events.fire("session_error", str(err))
            raise err
        finally:
            await self.stop()
