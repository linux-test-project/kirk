"""
.. module:: com
    :platform: Linux
    :synopsis: communication class definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import Any, Dict, List, Optional

import libkirk.plugin
from libkirk.errors import KirkException
from libkirk.plugin import Plugin

# discovered communication channels
_COM = []


class IOBuffer:
    """
    IO stdout buffer. The API is similar to ``IO`` types.
    """

    async def write(self, data: str) -> None:
        """
        Write ``data`` inside the buffer.
        """
        raise NotImplementedError()


class ComChannel(Plugin):
    """
    Communication channel. The objects implementing this class are usually
    using SSH, serial, shell, etc protocols. and they are used by the scheduler
    in order to execute commands or turning on/off the communication.
    """

    @property
    def parallel_execution(self) -> bool:
        """
        If True, communication supports commands parallel execution.
        """
        raise NotImplementedError()

    @property
    async def active(self) -> bool:
        """
        Return True if communication is active. False otherwise.
        """
        raise NotImplementedError()

    async def communicate(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Start communication.

        :param iobuffer: buffer used to write stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Stop communication.

        :param iobuffer: buffer used to write stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def ping(self) -> float:
        """
        Send a ping request and verify how much reply takes in seconds.
        :returns: float
        """
        raise NotImplementedError()

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        iobuffer: Optional[IOBuffer] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run a command.

        :param command: command to execute
        :type command: str
        :param cwd: current working directory
        :type cwd: str
        :param env: environment variables
        :type env: dict
        :param iobuffer: buffer used to write stdout
        :type iobuffer: IOBuffer
        :returns: dictionary containing command execution information

            {
                "command": <str>,
                "returncode": <int>,
                "stdout": <str>,
                "exec_time": <float>,
            }

            If None is returned, then callback failed.
        """
        raise NotImplementedError()

    async def fetch_file(self, target_path: str) -> bytes:
        """
        Fetch file and return its content.

        :param target_path: path of the file to download from target
        :type target_path: str
        :returns: bytes contained in target_path
        """
        raise NotImplementedError()

    async def ensure_communicate(
        self, iobuffer: Optional[IOBuffer] = None, retries: int = 10
    ) -> None:
        """
        Ensure that ``communicate`` is completed, retrying as many times we
        want in case of ``KirkException`` error. After each error, the
        communication is stopped and a new communication is performed.

        :param iobuffer: buffer used to write stdout
        :type iobuffer: IOBuffer
        :param retries: number of times we retry to communicate
        :type retries: int
        """
        retries = max(retries, 1)

        for retry in range(retries):
            try:
                await self.communicate(iobuffer=iobuffer)
                break
            except KirkException as err:
                if retry >= retries - 1:
                    raise err

                await self.stop(iobuffer=iobuffer)


def discover(path: str, extend: bool = True) -> None:
    """
    Discover all ComChannel implementations inside `path`.
    :param path: directory where searching for channel implementations
    :type path: str
    :param extend: if True, it will add new discovered channels on top of the
        ones already found. If False, previous discovered channels will be
        cleared.
    """
    global _COM

    obj = libkirk.plugin.discover(ComChannel, path)
    if not extend:
        _COM.clear()

    _COM.extend(obj)


def get_channels() -> List[ComChannel]:
    """
    :return: list of loaded ComChannel implementations.
    """
    global _COM
    # pyrefly: ignore[bad-return]
    return _COM
