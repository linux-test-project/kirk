"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import asyncio
import logging
import importlib
from libkirk.sut import SUT
from libkirk.sut import SUTError
from libkirk.sut import IOBuffer
from libkirk.ltx import Request
from libkirk.ltx import Requests
from libkirk.ltx import LTX
from libkirk.ltx import LTXError


class LTXSUT(SUT):
    """
    A SUT using LTX as executor.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.ltx")
        self._release_lock = asyncio.Lock()
        self._fetch_lock = asyncio.Lock()
        self._stdout = ''
        self._stdin = ''
        self._stdout_fd = -1
        self._stdin_fd = -1
        self._tmpdir = None
        self._ltx = None
        self._slots = []

    @property
    def name(self) -> str:
        return "ltx"

    @property
    def config_help(self) -> dict:
        return {
            "stdin": "transport stdin file",
            "stdout": "transport stdout file",
        }

    def setup(self, **kwargs: dict) -> None:
        if not importlib.util.find_spec('msgpack'):
            raise SUTError("'msgpack' library is not available")

        self._logger.info("Initialize SUT")

        self._tmpdir = kwargs.get("tmpdir", None)
        self._stdin = kwargs.get("stdin", None)
        self._stdout = kwargs.get("stdout", None)

        if not os.path.exists(self._stdin):
            raise SUTError(f"'{self._stdin}' stdin file doesn't exist")

        if not os.path.exists(self._stdout):
            raise SUTError(f"'{self._stdout}' stdout file doesn't exist")

    @property
    def parallel_execution(self) -> bool:
        return True

    @property
    async def is_running(self) -> bool:
        if self._ltx:
            return self._ltx.connected

        return False

    async def stop(self, iobuffer: IOBuffer = None) -> None:
        if not await self.is_running:
            return

        if self._slots:
            requests = []
            for slot_id in self._slots:
                requests.append(Requests.kill(slot_id))

            if requests:
                await self._send_requests(requests)

                while self._slots:
                    await asyncio.sleep(1e-2)

        try:
            await self._ltx.disconnect()
        except LTXError as err:
            raise SUTError(err)

        while await self.is_running:
            await asyncio.sleep(1e-2)

        try:
            if self._stdin_fd != -1:
                os.close(self._stdin_fd)

            if self._stdout_fd != -1:
                os.close(self._stdout_fd)
        except OSError as err:
            # LTX can exit before we close file, so we skip
            # 'Bad file descriptor' error message
            if err.errno == 9:
                pass

    async def _send_requests(self, requests: list) -> list:
        """
        Send requests and check for LTXError.
        """
        reply = None
        try:
            reply = await self._ltx.gather(requests)
        except LTXError as err:
            raise SUTError(err)

        return reply

    async def _reserve_slot(self) -> int:
        """
        Reserve an execution slot.
        """
        async with self._release_lock:
            slot_id = -1
            for i in range(0, Request.MAX_SLOTS):
                if i not in self._slots:
                    slot_id = i
                    break

            if slot_id == -1:
                raise SUTError("No execution slots available")

            self._slots.append(slot_id)

            return slot_id

    async def _release_slot(self, slot_id: int) -> None:
        """
        Release an execution slot.
        """
        if slot_id in self._slots:
            self._slots.remove(slot_id)

    async def ping(self) -> float:
        if not await self.is_running:
            raise SUTError("SUT is not running")

        req = Requests.ping()
        start_t = time.monotonic()
        replies = await self._send_requests([req])

        return (replies[req][0] * 1e-9) - start_t

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is already running")

        self._stdin_fd = os.open(self._stdin, os.O_WRONLY)
        self._stdout_fd = os.open(self._stdout, os.O_RDONLY)

        self._ltx = LTX(self._stdin_fd, self._stdout_fd)

        try:
            await self._ltx.connect()
        except LTXError as err:
            raise SUTError(err)

        await self._send_requests([Requests.version()])

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

        self._logger.info("Running command: %s", repr(command))

        slot_id = await self._reserve_slot()
        ret = None

        try:
            start_t = time.monotonic()

            requests = []
            if cwd:
                requests.append(Requests.cwd(slot_id, cwd))

            if env:
                for key, value in env.items():
                    requests.append(Requests.env(slot_id, key, value))

            async def _stdout_coro(data):
                if iobuffer:
                    await iobuffer.write(data)

            exec_req = Requests.execute(
                slot_id,
                command,
                stdout_coro=_stdout_coro)

            requests.append(exec_req)
            replies = await self._send_requests(requests)
            reply = replies[exec_req]

            ret = {
                "command": command,
                "stdout": reply[3],
                "exec_time": (reply[0] * 1e-9) - start_t,
                "returncode": reply[2],
            }

            self._logger.debug(ret)
        finally:
            await self._release_slot(slot_id)

        self._logger.info("Command executed")

        return ret

    async def fetch_file(self, target_path: str) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not await self.is_running:
            raise SUTError("SSH connection is not present")

        async with self._fetch_lock:
            req = Requests.get_file(target_path)
            replies = await self._send_requests([req])
            reply = replies[req]

            return reply[1]
