"""
.. module:: io
    :platform: Linux
    :synopsis: module for handling I/O blocking operations

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from types import TracebackType
from typing import (
    IO,
    Any,
    AsyncContextManager,
    Optional,
    Type,
    Union,
)

import libkirk


class AsyncFile(AsyncContextManager):
    """
    Handle files in asynchronous way by running operations inside a separate
    thread.
    """

    def __init__(self, filename: str, mode: str = "r") -> None:
        """
        :param filename: Location of the file to open.
        :type filename: str
        :param mode: Mode used to open the file.
        :type mode: str
        """
        self._filename = filename
        self._mode = mode
        self._file = None

    async def __aenter__(self) -> Any:
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        await self.close()
        return True

    def __aiter__(self) -> Any:
        return self

    async def __anext__(self) -> Optional[Union[str, bytes]]:
        if "r" not in self._mode:
            raise ValueError("File must be open in read mode")

        line = None
        if self._file:
            line = await libkirk.to_thread(self._file.readline)
            if not line:
                raise StopAsyncIteration()

            if isinstance(line, str):
                return str(line)
            elif isinstance(line, bytes):
                return bytes(line)
            else:
                raise ValueError("File is not handling str | bytes")

        return None

    async def open(self) -> None:
        """
        Open the file according to the mode.
        """
        if self._file:
            return

        def _open() -> IO[Any]:
            if "b" in self._mode:
                return open(self._filename, self._mode)

            return open(self._filename, self._mode, encoding="utf-8")

        self._file = await libkirk.to_thread(_open)

    async def close(self) -> None:
        """
        Close the file.
        """
        if not self._file:
            return

        await libkirk.to_thread(self._file.close)
        self._file = None

    async def seek(self, pos: int) -> None:
        """
        Asynchronous version of `seek()`.

        :param pos: Position to search.
        :type pos: int
        """
        if not self._file:
            return

        await libkirk.to_thread(self._file.seek, pos)

    async def tell(self) -> Optional[int]:
        """
        Asynchronous version of `tell()`.

        :return: Current file position or None if file is not open.
        :rtype: int | None
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.tell)

    async def read(self, size: int = -1) -> Optional[Union[str, bytes]]:
        """
        Asynchronous version of `read()`.

        :param size: Amount of data to read. Default is -1, that means all data
            available.
        :type size: int
        :returns: Data that has been read or None if file is not open.
        :rtype: str | bytes | None
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.read, size)

    async def readline(self) -> Optional[Union[str, bytes]]:
        """
        Asynchronous version of `readline()`.

        :returns: Data that has been read or None if file is not open.
        :rtype: str | bytes | None
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.readline)

    async def write(self, data: Union[str, bytes]) -> None:
        """
        Asynchronous version of `write()`.

        :param data: Data to write inside file.
        :type data: str | bytes
        """
        if not self._file:
            return

        await libkirk.to_thread(self._file.write, data)
