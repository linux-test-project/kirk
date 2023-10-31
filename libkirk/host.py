"""
.. module:: host
    :platform: Linux
    :synopsis: module containing host SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import signal
import asyncio
import logging
import contextlib
from asyncio.subprocess import Process
from libkirk.sut import SUT
from libkirk.sut import IOBuffer
from libkirk.sut import SUTError
from libkirk.sut import KernelPanicError


class HostSUT(SUT):
    """
    SUT implementation using host's shell.
    """
    BUFFSIZE = 1024

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.host")
        self._fetch_lock = asyncio.Lock()
        self._procs = []
        self._running = False
        self._stop = False

    def setup(self, **kwargs: dict) -> None:
        pass

    @property
    def config_help(self) -> dict:
        # cwd and env are given by default, so no options are needed
        return {}

    @property
    def name(self) -> str:
        return "host"

    @property
    def parallel_execution(self) -> bool:
        return True

    @property
    async def is_running(self) -> bool:
        return self._running

    @staticmethod
    async def _process_alive(proc: Process) -> bool:
        """
        Return True if process is alive and running.
        """
        with contextlib.suppress(asyncio.TimeoutError):
            returncode = await asyncio.wait_for(proc.wait(), 1e-6)
            if returncode is not None:
                return False

        return True

    async def _kill_process(self, proc: Process) -> None:
        """
        Kill a process and all its subprocesses.
        """
        self._logger.info("Kill process %d", proc.pid)

        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except ProcessLookupError:
            # process has been killed already
            pass

    async def ping(self) -> float:
        if not await self.is_running:
            raise SUTError("SUT is not running")

        ret = await self.run_command("test .")
        reply_t = ret["exec_time"]

        return reply_t

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is running")

        self._running = True

    async def stop(self, iobuffer: IOBuffer = None) -> None:
        if not await self.is_running:
            return

        self._logger.info("Stopping SUT")
        self._stop = True

        try:
            if self._procs:
                self._logger.info(
                    "Terminating %d process(es)",
                    len(self._procs))

                for proc in self._procs:
                    await self._kill_process(proc)

                await asyncio.gather(*[
                    proc.wait() for proc in self._procs
                ])

                self._logger.info("Process(es) terminated")

            if self._fetch_lock.locked():
                self._logging.info("Terminating data fetch")

                async with self._fetch_lock:
                    pass
        finally:
            self._stop = False
            self._running = False
            self._logger.info("SUT has stopped")

    async def run_command(
            self,
            command: str,
            cwd: str = None,
            env: dict = None,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("SUT is not running")

        self._logger.info("Executing command: '%s'", command)

        ret = None
        proc = None
        t_end = 0
        stdout = ""

        try:
            kwargs = {
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.STDOUT,
                "cwd": cwd,
                "preexec_fn": os.setsid
            }

            if env:
                # commands can fail when env is defined, so we just skip
                # env usage if dictionary is empty
                kwargs["env"] = env

            proc = await asyncio.create_subprocess_shell(command, **kwargs)

            self._procs.append(proc)

            t_start = time.time()
            panic = False

            while True:
                line = await proc.stdout.read(self.BUFFSIZE)
                sline = line.decode(encoding="utf-8", errors="ignore")

                if iobuffer:
                    await iobuffer.write(sline)

                stdout += sline
                panic = "Kernel panic" in stdout[-2*self.BUFFSIZE:]

                if not await self._process_alive(proc):
                    break

            await proc.wait()

            t_end = time.time() - t_start

            if panic:
                raise KernelPanicError()
        finally:
            if proc:
                self._procs.remove(proc)

                await self._kill_process(proc)
                await proc.wait()

                ret = {
                    "command": command,
                    "stdout": stdout,
                    "returncode": proc.returncode,
                    "exec_time": t_end,
                }

                self._logger.debug("return data=%s", ret)

        self._logger.info("Command executed")

        return ret

    async def fetch_file(self, target_path: str) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not os.path.isfile(target_path):
            raise SUTError(f"'{target_path}' file doesn't exist")

        if not await self.is_running:
            raise SUTError("SUT is not running")

        async with self._fetch_lock:
            self._logger.info("Downloading '%s'", target_path)

            retdata = bytes()

            try:
                with open(target_path, 'rb') as ftarget:
                    retdata = ftarget.read()
            except IOError as err:
                raise SUTError(err)

            self._logger.info("File copied")

            return retdata
