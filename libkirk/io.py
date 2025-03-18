"""
.. module:: io
    :platform: Linux
    :synopsis: module for handling I/O blocking operations

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import libkirk


class AsyncFile:
    """
    Handle files in asynchronous way by running operations inside a separate
    thread.
    """

    def __init__(self, filename: str, mode='r') -> None:
        """
        :param filename: file to open
        :type filename: str
        :param mode: mode to open the file
        :type mode: str
        """
        self._filename = filename
        self._mode = mode
        self._file = None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if 'r' not in self._mode:
            raise ValueError("File must be open in read mode")

        line = None
        if self._file:
            line = await libkirk.to_thread(self._file.readline)
            if not line:
                raise StopAsyncIteration

        return line

    async def open(self) -> None:
        """
        Open the file according to the mode.
        """
        if self._file:
            return

        def _open():
            if 'b' in self._mode:
                # pylint: disable=unspecified-encoding
                return open(self._filename, self._mode)

            return open(self._filename, self._mode, encoding='utf-8')

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
        :param pos: position to search
        :type pos: int
        """
        if not self._file:
            return

        await libkirk.to_thread(self._file.seek, pos)

    async def tell(self) -> int:
        """
        Asynchronous version of `tell()`.
        :returns: current file position or None if file is not open.
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.tell)

    async def read(self, size: int = -1) -> str:
        """
        Asynchronous version of `read()`.
        :returns: data that has been read or None if file is not open.
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.read, size)

    async def readline(self) -> str:
        """
        Asynchronous version of `readline()`.
        :returns: data that has been read or None if file is not open.
        """
        if not self._file:
            return None

        return await libkirk.to_thread(self._file.readline)

    async def write(self, data: str) -> None:
        """
        Asynchronous version of `write()`.
        :param data: data to write inside file
        :type data: str
        """
        if not self._file:
            return

        await libkirk.to_thread(self._file.write, data)
