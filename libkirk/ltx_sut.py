"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import importlib.util
import logging
import os
import time
from typing import Any, Dict, List, Optional

import libkirk.types
from libkirk.errors import LTXError, SUTError
from libkirk.ltx import LTX, Request, Requests
from libkirk.sut import SUT, IOBuffer


class LTXSUT(SUT):
    """
    A SUT using LTX as executor.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.ltx")
        self._release_lock = asyncio.Lock()
        self._fetch_lock = asyncio.Lock()
        self._ltx: Optional[LTX] = None
        self._outfile = ""
        self._infile = ""
        self._slots = []

    @property
    def name(self) -> str:
        return "ltx"

    @property
    def config_help(self) -> Dict[str, str]:
        return {
            "infile": "file where ltx is reading data",
            "outfile": "file where ltx is writing data",
        }

    def setup(self, **kwargs: Dict[str, Any]) -> None:
        if not importlib.util.find_spec("msgpack"):
            raise SUTError("'msgpack' library is not available")

        self._logger.info("Initialize SUT")

        self._infile = libkirk.types.dict_item(kwargs, "infile", str)
        self._outfile = libkirk.types.dict_item(kwargs, "outfile", str)

        if not self._infile or not os.path.exists(self._infile):
            raise SUTError(f"'{self._infile}' input file doesn't exist")

        if not self._outfile or not os.path.exists(self._outfile):
            raise SUTError(f"'{self._outfile}' output file doesn't exist")

    @property
    def parallel_execution(self) -> bool:
        return True

    @property
    async def is_running(self) -> bool:
        if not self._ltx:
            return False

        return self._ltx.connected

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
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
            # pyrefly: ignore[missing-attribute]
            await self._ltx.disconnect()
        except LTXError as err:
            raise SUTError(err) from err

        while await self.is_running:
            await asyncio.sleep(1e-2)

    async def _send_requests(self, requests: List[Request]) -> Dict[Request, Any]:
        """
        Send requests and check for LTXError.
        """
        reply = None
        try:
            # pyrefly: ignore[missing-attribute]
            reply = await self._ltx.gather(requests)
        except LTXError as err:
            raise SUTError(err) from err

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

    async def communicate(self, iobuffer: Optional[IOBuffer] = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is already running")

        self._ltx = LTX(self._infile, self._outfile)

        try:
            await self._ltx.connect()
        except LTXError as err:
            raise SUTError(err) from err

        await self._send_requests([Requests.version()])

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        iobuffer: Optional[IOBuffer] = None,
    ) -> Optional[Dict[str, Any]]:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("SUT is not running")

        self._logger.info("Running command: %s", repr(command))

        slot_id = await self._reserve_slot()
        ret = None

        try:
            start_t = time.monotonic()

            requests: List[Request] = []
            if cwd:
                requests.append(Requests.cwd(slot_id, cwd))

            if env:
                for key, value in env.items():
                    requests.append(Requests.env(slot_id, key, value))

            async def _stdout_coro(data):
                if iobuffer:
                    await iobuffer.write(data)

            exec_req = Requests.execute(slot_id, command, stdout_coro=_stdout_coro)

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
