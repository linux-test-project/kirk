"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import asyncio
import logging
import typing
import libkirk

try:
    import msgpack
except ModuleNotFoundError:
    pass


class LTXError(Exception):
    """
    Raised when an error occurs during LTX execution.
    """


class Request:
    """
    LTX request.
    """
    ERROR = 0xff
    VERSION = 0x00
    PING = 0x01
    PONG = 0x02
    GET_FILE = 0x03
    SET_FILE = 0x04
    ENV = 0x05
    CWD = 0x06
    EXEC = 0x07
    RESULT = 0x08
    LOG = 0x09
    DATA = 0xa0
    KILL = 0xa1
    MAX_SLOTS = 127
    ALL_SLOTS = 128
    MAX_ENVS = 16

    def __init__(self) -> None:
        self._logger = logging.getLogger("ltx.request")
        self._completed = False
        self._done_coro = []

    @property
    def completed(self) -> bool:
        """
        If True the request has been completed.
        """
        return self._completed

    def add_done_coro(self, coro: typing.Coroutine) -> None:
        """
        Add done event to request.
        :param coro: called when request is done
        :type coro: Coroutine
        """
        self._done_coro.append(coro)

    async def _raise_complete(self, *args) -> None:
        """
        Raise the complete callback with given data.
        """
        if self._done_coro:
            self._logger.info("Raising 'on_complete(self, %s)'", args)

            for coro in self._done_coro:
                await coro(self, *args)

        self._completed = True

    async def pack(self) -> bytes:
        """
        Pack LTX request into bytes.
        """
        raise NotImplementedError()

    async def feed(self, message: list) -> None:
        """
        Feed request queue with data and return when the request
        has been completed.
        :param message: processed msgpack message
        :type message: list
        """
        raise NotImplementedError()

# pylint: disable=invalid-name


class Requests:
    """
    Class container for LTX requests.
    """
    class version(Request):
        """
        VERSION request.
        """

        async def pack(self) -> bytes:
            return msgpack.packb([self.VERSION])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.VERSION:
                ver = message[1]

                self._logger.debug("version=%s", ver)
                await self._raise_complete(ver)

    class ping(Request):
        """
        PING request.
        """

        def __init__(self) -> None:
            super().__init__()
            self._echoed = False

        async def pack(self) -> bytes:
            return msgpack.packb([self.PING])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.PING:
                self._logger.info("PING echoed back")
                self._logger.info("Waiting for PONG")
                self._echoed = True
            elif message[0] == self.PONG:
                if not self._echoed:
                    raise LTXError("PONG received without PING echo")

                end_t = message[1]

                self._logger.debug("end_t=%s", end_t)
                await self._raise_complete(end_t)

    class env(Request):
        """
        ENV request.
        """

        def __init__(self, slot_id: int, key: str, value: str) -> None:
            """
            :param slot_id: command table ID. Can be None if we want to apply
                the same environment variable to all executions
            :type slot_id: int
            :param key: key of the environment variable
            :type key: str
            :param value: value of the environment variable
            :type value: str
            """
            super().__init__()

            if slot_id and (slot_id < 0 or slot_id > self.ALL_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.ALL_SLOTS}]")

            if not key:
                raise ValueError("key is empty")

            if not value:
                raise ValueError("value is empty")

            self._slot_id = self.ALL_SLOTS if slot_id is None else slot_id
            self._key = key
            self._value = value

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.ENV,
                self._slot_id,
                self._key,
                self._value
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.ENV:
                self._logger.info("ENV echoed back")
                await self._raise_complete(
                    self._slot_id,
                    self._key,
                    self._value)

    class cwd(Request):
        """
        CWD request.
        """

        def __init__(self, slot_id: int, path: str) -> None:
            """
            :param slot_id: command table ID. Can be None if we want to apply
                the same current working directory to all executions
            :type slot_id: int
            :param path: current working path
            :type path: str
            """
            super().__init__()

            if slot_id is not None and \
                    (slot_id < 0 or slot_id > self.ALL_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.ALL_SLOTS}]")

            if not path:
                raise ValueError("path is empty")

            self._slot_id = self.ALL_SLOTS if slot_id is None else slot_id
            self._path = path

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.CWD,
                self._slot_id,
                self._path,
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.CWD:
                self._logger.info("CWD echoed back")
                await self._raise_complete(self._slot_id, self._path)

    class get_file(Request):
        """
        GET_FILE request.
        """

        def __init__(self, path: str) -> None:
            """
            :param path: path of the file to read
            :type path: str
            """
            super().__init__()

            if not path:
                raise ValueError("path is empty")

            self._path = path
            self._data = []

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.GET_FILE,
                self._path,
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.DATA:
                self._logger.info("Data received")
                self._data.append(message[1])
            elif message[0] == self.GET_FILE:
                self._logger.info("GET_FILE echoed back")
                await self._raise_complete(self._path, b''.join(self._data))

    class set_file(Request):
        """
        SET_FILE request.
        """

        def __init__(self, path: str, data: bytes) -> None:
            """
            :param path: path of the file to write
            :type path: str
            :param data: data to write on file
            :type data: bytes
            """
            super().__init__()

            if not path:
                raise ValueError("path is empty")

            if not data:
                raise ValueError("data is empty")

            self._path = path
            self._data = data

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.SET_FILE,
                self._path,
                self._data,
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.SET_FILE and message[1] == self._path:
                self._logger.info("SET_FILE echoed back")
                await self._raise_complete(self._path, self._data)

    class execute(Request):
        """
        EXEC request.
        """

        def __init__(
                self,
                slot_id: int,
                command: str,
                stdout_coro: typing.Coroutine = None) -> None:
            """
            :param slot_id: command table ID
            :type slot_id: int
            :param command: command to run
            :type command: str
            :param stdout_coro: called when new data arrives in stdout
            :type stdout_coro: callable
            """
            super().__init__()

            if slot_id is None:
                raise ValueError("slot_id is empty")

            if slot_id < 0 or slot_id > self.MAX_SLOTS:
                raise ValueError(f"Out of bounds slot ID [0-{self.MAX_SLOTS}]")

            if not command:
                raise ValueError("Command is empty")

            self._slot_id = slot_id
            self._command = command
            self._stdout_coro = stdout_coro
            self._stdout = []
            self._echoed = False

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.EXEC,
                self._slot_id,
                self._command,
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.EXEC:
                self._logger.info("EXEC echoed back")
                self._echoed = True
            elif message[0] == self.LOG:
                if not self._echoed:
                    raise LTXError("LOG received without EXEC echo")

                log = message[3]

                if log:
                    self._logger.info("LOG replied with data: %s", repr(log))
                    self._stdout.append(log)

                    if self._stdout_coro:
                        await self._stdout_coro(log)
            elif message[0] == self.RESULT:
                if not self._echoed:
                    raise LTXError("RESULT received without EXEC echo")

                self._logger.info("RESULT received")

                stdout = "".join(self._stdout)
                time_ns = message[2]
                si_code = message[3]
                si_status = message[4]

                self._logger.debug(
                    "time_ns=%s, si_code=%s, si_status=%s",
                    time_ns,
                    si_code,
                    si_status)

                await self._raise_complete(
                    time_ns,
                    si_code,
                    si_status,
                    stdout)

    class kill(Request):
        """
        KILL request.
        """

        def __init__(self, slot_id: int) -> None:
            """
            :param slot_id: command table ID
            :type slot_id: int
            """
            super().__init__()

            if slot_id is None:
                raise ValueError("slot_id is empty")

            if slot_id < 0 or slot_id > self.MAX_SLOTS:
                raise ValueError(f"Out of bounds slot ID [0-{self.MAX_SLOTS}]")

            self._slot_id = slot_id

        async def pack(self) -> bytes:
            return msgpack.packb([
                self.KILL,
                self._slot_id,
            ])

        async def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.KILL:
                self._logger.info("KILL echoed back")
                await self._raise_complete(self._slot_id)


class LTX:
    """
    This class communicates with LTX by processing given requests.
    Typical usage is the following:
    ```
    async with LTX(stdin_fd, stdout_fd) as ltx:
        # create requests
        request1 = Requests.execute("echo 'hello world' > myfile")
        request2 = Requests.get_file("myfile")

        # set the complete event
        request1.add_done_coro(exec_complete_handler)
        request2.add_done_coro(get_file_complete_handler)

        # send request
        ltx.send([request1, request2])

        # process events output
        ...
    ```
    """
    BUFFSIZE = 1 << 21

    def __init__(self, stdin_fd: int, stdout_fd: int) -> None:
        self._logger = logging.getLogger("ltx")
        self._requests = []
        self._stop = False
        self._stdin_fd = stdin_fd
        self._stdout_fd = stdout_fd
        self._lock = asyncio.Lock()
        self._task = None
        self._messages = []
        self._exception = None

    async def __aenter__(self) -> None:
        """
        Connect to the LTX service.
        """
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Disconnect from LTX service.
        """
        await self.disconnect()

    @property
    def connected(self) -> bool:
        """
        True if connected, False otherwise.
        """
        if not self._task:
            return False

        return not self._task.done()

    async def connect(self) -> None:
        """
        Connect to LTX.
        """
        if self.connected:
            return

        self._logger.info("Connecting to LTX")

        os.set_blocking(self._stdout_fd, False)

        self._exception = None
        self._task = libkirk.create_task(self._polling())

        if self._exception:
            raise self._exception

        self._logger.info("Connected")

    async def disconnect(self) -> None:
        """
        Disconnect from LTX service.
        """
        if not self.connected:
            return

        self._logger.info("Disconnecting")
        self._stop = True

        while self.connected:
            await asyncio.sleep(0.005)
            if self._exception:
                raise self._exception

        if self._exception:
            raise self._exception

        self._logger.info("Disconnected")

    async def send(self, requests: list) -> None:
        """
        Send requests to LTX service. The order is preserved during
        requests execution.
        :param requests: list of requests to send
        :type requests: list
        """
        if not requests:
            raise ValueError("No requests given")

        if not self.connected:
            raise LTXError("Client is not connected to LTX")

        async with self._lock:
            self._logger.info("Sending requests")
            self._requests.extend(requests)

            data = [await req.pack() for req in requests]
            tosend = b''.join(data)

            await self._write(bytes(tosend))

    async def gather(self, requests: list) -> dict:
        """
        Gather multiple requests and wait for the response, then return all
        rquests' replies inside a dictionary that maps requests with their
        reply.
        """
        req_len = len(requests)
        replies = {}

        async def on_complete(req, *args):
            replies[req] = args

        for req in requests:
            req.add_done_coro(on_complete)

        await self.send(requests)

        while len(replies) != req_len:
            await asyncio.sleep(0.005)
            if self._exception:
                raise self._exception

        if self._exception:
            raise self._exception

        return replies

    async def _read(self, size: int) -> bytes:
        """
        Blocking I/O method to read from stdout.
        """
        data = None
        try:
            data = await libkirk.to_thread(os.read, self._stdout_fd, size)
        except BlockingIOError:
            # we ensure other threads will take action if reading
            # procedure is too fast for this process
            os.sched_yield()

        return data

    async def _write(self, data: bytes) -> None:
        """
        Blocking I/O method to write on stdin.
        """
        towrite = len(data)
        try:
            wrote = await libkirk.to_thread(os.write, self._stdin_fd, data)

            if towrite != wrote:
                raise LTXError(f"Wrote {wrote} bytes but expected {towrite}")
        except BrokenPipeError:
            pass

    # pylint: disable=too-many-nested-blocks
    async def _polling(self) -> None:
        """
        Read and process messages coming from LTX stdout.
        """
        self._logger.info("Starting producer")

        # force utf-8 encoding by using raw=False
        unpacker = msgpack.Unpacker(raw=False)

        try:
            while not self._stop:
                data = await self._read(self.BUFFSIZE)
                if not data:
                    continue

                self._logger.debug("Unpacking bytes: %s", data)

                unpacker.feed(data)

                while True:
                    try:
                        msg = unpacker.unpack()
                        if not msg:
                            continue

                        self._logger.info("Received message: %s", msg)
                        if not isinstance(msg, list):
                            raise LTXError("Message must be an array")

                        if msg[0] == Request.ERROR:
                            raise LTXError(msg[1])

                        await self._feed_requests(msg)
                    except msgpack.OutOfData:
                        break
        except LTXError as err:
            self._exception = err
        finally:
            self._logger.info("Producer has stopped")

    async def _feed_requests(self, data: list) -> None:
        """
        Feed the list of requests with given data.
        """
        pos = 0
        while pos < len(self._requests):
            request = self._requests[pos]
            await request.feed(data)

            if request.completed:
                del self._requests[pos]
            else:
                pos += 1
