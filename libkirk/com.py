"""
.. module:: com
    :platform: Linux
    :synopsis: communication class definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

import libkirk.plugin
from libkirk.errors import (
    KirkException,
    PluginError,
)
from libkirk.plugin import Plugin

# discovered communication channels
_COM = []


class IOBuffer:
    """
    IO stdout buffer. The API is similar to IO types.
    """

    async def write(self, data: str) -> None:
        """
        Write data inside the buffer.

        :param data: Data to write.
        :type data: str
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
        :return: If True, communication supports commands parallel execution.
        :rtype: bool
        """
        raise NotImplementedError()

    @property
    async def active(self) -> bool:
        """
        :return: Return True if communication is active. False otherwise.
        :rtype: bool
        """
        raise NotImplementedError()

    async def communicate(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Start communication.

        :param iobuffer: Buffer used to write stdout.
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Stop communication.

        :param iobuffer: Buffer used to write stdout.
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def ping(self) -> float:
        """
        Send a ping request and verify how much reply takes in seconds.

        :return: Time between ping and pong.
        :rtype: float
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

        :param command: Command to execute.
        :type command: str
        :param cwd: Current working directory.
        :type cwd: str
        :param env: Environment variables.
        :type env: dict
        :param iobuffer: Buffer used to write stdout.
        :type iobuffer: IOBuffer
        :return: Dictionary containing information about the executed command.

            .. code-block:: python

                {
                    "command": <str>,
                    "returncode": <int>,
                    "stdout": <str>,
                    "exec_time": <float>,
                }

            If None is returned, then callback has failed.
        :rtype: dict
        """
        raise NotImplementedError()

    async def fetch_file(self, target_path: str) -> bytes:
        """
        Fetch file and return its content.

        :param target_path: Path of the file to download from target.
        :type target_path: str
        :return: Data contained in target_path.
        :rtype: bytes
        """
        raise NotImplementedError()

    async def ensure_communicate(
        self, iobuffer: Optional[IOBuffer] = None, retries: int = 10
    ) -> None:
        """
        Ensure that communicate is completed, retrying as many times we
        want in case of KirkException error. After each error, the
        communication is stopped and a new communication is performed.

        :param iobuffer: Buffer used to write stdout.
        :type iobuffer: IOBuffer
        :param retries: Number of times we retry to communicate.
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

    :param path: Directory where searching for channel implementations.
    :type path: str
    :param extend: If True, it will add new discovered channels on top of the
        ones already found. If False, previous discovered channels will be
        cleared.
    :rtype: bool
    """
    global _COM

    obj = libkirk.plugin.discover(ComChannel, path)
    if not extend:
        _COM.clear()

    _COM.extend(obj)


def get_channels() -> List[ComChannel]:
    """
    :return: List of loaded ComChannel implementations.
    :rtype: list(ComChannel)
    """
    global _COM
    # pyrefly: ignore[bad-return]
    return _COM


def clone_channel(name: str, new_name: str) -> Plugin:
    """
    Clone a channel implementation named name and rename it with
    new_name. The new plugin will be registered with the other
    plugins.

    :param name: Plugin name.
    :type name: str
    :param new_name: New cloned plugin name.
    :type new_name: str
    :return: New plugin object.
    :rtype: Plugin
    """
    global _COM

    plugin = next((c for c in _COM if c.name == name), None)
    if not plugin:
        raise PluginError(f"Can't find plugin '{name}'")

    channel = plugin.clone(new_name)
    _COM.append(channel)

    return channel
