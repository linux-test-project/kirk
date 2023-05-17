"""
.. module:: ltx
    :platform: Linux
    :synopsis: module containing LTX communication class

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import select
import asyncio
import logging
import importlib
import kirk
from kirk.sut import SUT
from kirk.sut import SUTError
from kirk.sut import IOBuffer

try:
    import msgpack
except ModuleNotFoundError:
    pass


class LTXError(kirk.KirkException):
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
    MAX_SLOTS = 128
    ALL_SLOTS = 128
    MAX_ENVS = 16

    def __init__(self, **kwargs: dict) -> None:
        """
        :param args: request arguments
        :type args: list
        """
        self._logger = logging.getLogger("ltx.request")
        self._request_id = None
        self._args = kwargs.get("args", [])
        self._completed = False
        self._on_complete = None

    @property
    def completed(self) -> bool:
        """
        If True the request has been completed.
        """
        return self._completed

    @property
    def on_complete(self) -> callable:
        """
        Get the `on_complete` event.
        """
        return self._on_complete

    @on_complete.setter
    def on_complete(self, callback: callable) -> None:
        """
        Set the `on_complete` event.
        """
        self._on_complete = callback

    def pack(self) -> bytes:
        """
        Pack request to msgpack.
        """
        msg = []
        msg.append(self._request_id)
        msg.extend(self._args)

        data = msgpack.packb(msg)

        return data

    def _raise_complete(self, *args) -> None:
        """
        Raise the complete callback with given data.
        """
        if self._on_complete:
            self._logger.info("Raising 'on_complete(self, %s)'", args)
            self._on_complete(self, *args)

        self._completed = True

    def check_error(self, message: list) -> None:
        """
        Check if given message is an error and eventually raise an error.
        :param message: processed msgpack message
        :type message: list
        """
        if message[0] == self.ERROR:
            raise LTXError(message[1])

    def feed(self, message: list) -> None:
        """
        Feed request queue with data and return when the request
        has been completed.
        :param message: processed msgpack message
        :type message: list
        """
        raise NotImplementedError()


def version() -> Request:
    """
    Create VERSION request.
    :returns: Request
    """
    class _VersionRequest(Request):
        """
        VERSION request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.VERSION

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self._request_id:
                ver = message[1]
                self._logger.debug("version=%s", ver)

                self._raise_complete(ver)
                self._completed = True

    return _VersionRequest()


def ping() -> Request:
    """
    Create PING request.
    :returns: Request
    """
    class _PingRequest(Request):
        """
        PING request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._echoed = False
            self._request_id = self.PING

        def feed(self, message: list) -> None:
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

                self._raise_complete(end_t)
                self._completed = True

    return _PingRequest()


def env(slot_id: int, key: str, value: str) -> Request:
    """
    Create ENV request.
    :param slot_id: command table ID. Can be None if we want to apply the
        same environment variables to all commands
    :type slot_id: int
    :param key: key of the environment variable
    :type key: str
    :param value: value of the environment variable
    :type value: str
    :returns: Request
    """
    if not key:
        raise ValueError("key is empty")

    if not value:
        raise ValueError("value is empty")

    class _EnvRequest(Request):
        """
        ENV request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.ENV
            self._slot_id = self._args[0]

            if self._slot_id and \
                    (self._slot_id < 0 or self._slot_id > self.ALL_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.ALL_SLOTS}]")

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.ENV:
                self._logger.info("ENV echoed back")

                self._raise_complete()
                self._completed = True

    return _EnvRequest(args=[slot_id, key, value])


def cwd(slot_id: int, path: str) -> Request:
    """
    Create CWD request.
    :param slot_id: command table ID. Can be None if we want to apply the
        same environment variables to all commands
    :type slot_id: int
    :param path: current working path
    :type path: str
    :returns: Request
    """
    if not path:
        raise ValueError("path is empty")

    class _CwdRequest(Request):
        """
        CWD request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.CWD
            self._slot_id = self._args[0]

            if self._slot_id and \
                    (self._slot_id < 0 or self._slot_id > self.ALL_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.ALL_SLOTS}]")

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.CWD:
                self._logger.info("CWD echoed back")

                self._raise_complete()
                self._completed = True

    return _CwdRequest(args=[slot_id, path])


def get_file(path: str) -> Request:
    """
    Create GET_FILE request.
    :param path: path of the file
    :type path: str
    :returns: Request
    """
    if not path:
        raise ValueError("path is empty")

    class _GetFileRequest(Request):
        """
        GET_FILE request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.GET_FILE
            self._data = []

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.GET_FILE:
                self._logger.info("GET_FILE echoed back")
                self._completed = True

                self._raise_complete(b''.join(self._data))
                self._completed = True
            elif message[0] == self.DATA:
                self._logger.info("Data received")
                self._data.append(message[1])

    return _GetFileRequest(args=[path])


def set_file(path: str, data: bytes) -> Request:
    """
    Create SET_FILE request.
    :param path: path of the file to write
    :type path: str
    :param data: data to write on file
    :type data: bytes
    :returns: Request
    """
    if not path:
        raise ValueError("path is empty")

    if not data:
        raise ValueError("data is empty")

    class _SetFileRequest(Request):
        """
        SET_FILE request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.SET_FILE

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if message[0] == self.SET_FILE and message[1] == self._args[0]:
                self._logger.info("SETFILE echoed back")

                self._raise_complete()
                self._completed = True

    return _SetFileRequest(args=[path, data])


def execute(slot_id: int,
            command: str,
            stdout_callback: callable = None) -> Request:
    """
    Create EXEC request.
    :param slot_id: command table ID
    :type slot_id: int
    :param command: command to run
    :type command: str
    :param stdout_callback: called when new data arrives inside stdout
    :type stdout_callback: callable
    :returns: Request
    """
    if not command:
        raise ValueError("Command is empty")

    class _ExecRequest(Request):
        """
        EXEC request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._stdout_callback = kwargs.get("stdout_callback", None)
            self._stdout = []
            self._echoed = False
            self._request_id = self.EXEC
            self._slot_id = self._args[0]

            if self._slot_id and \
                    (self._slot_id < 0 or self._slot_id >= self.MAX_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.MAX_SLOTS}]")

        def feed(self, message: list) -> None:
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

                self._logger.info("LOG replied with data: %s", repr(log))
                self._stdout.append(log)

                if self._stdout_callback:
                    self._stdout_callback(log)
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

                self._raise_complete(
                    stdout,
                    time_ns,
                    si_code,
                    si_status)

                self._completed = True

    args = [slot_id, command]

    return _ExecRequest(stdout_callback=stdout_callback, args=args)


def kill(slot_id: int) -> Request:
    """
    Create KILL request.
    :param slot_id: command table ID
    :type slot_id: int
    :returns: Request
    """
    class _KillRequest(Request):
        """
        KILL request.
        """

        def __init__(self, **kwargs: dict) -> None:
            super().__init__(**kwargs)

            self._request_id = self.KILL
            self._slot_id = self._args[0]

            if self._slot_id and \
                    (self._slot_id < 0 or self._slot_id >= self.MAX_SLOTS):
                raise ValueError(f"Out of bounds slot ID [0-{self.MAX_SLOTS}]")

        def feed(self, message: list) -> None:
            if self.completed:
                return

            if len(message) > 1 and message[1] != self._slot_id:
                return

            if message[0] == self.KILL:
                self._logger.info("KILL echoed back")

                self._raise_complete()
                self._completed = True

    return _KillRequest(args=[slot_id])


class Session:
    """
    This class communicates with LTX by processing given requests.
    Typical usage is the following:

        with ltx.Session(stdin_fd, stdout_fd) as session:
            # create requests
            request1 = ltx.execute("echo 'hello world' > myfile")
            request2 = ltx.get_file("myfile")

            # set the complete event
            request1.on_complete = exec_complete_handler
            request2.on_complete = get_file_complete_handler

            # send request
            session.send([request1, request2])

            # process exec_complete_handler/get_file_complete_handler output
            ...

    """
    BUFFSIZE = 1 << 21

    def __init__(self, stdin_fd: int, stdout_fd: int) -> None:
        self._logger = logging.getLogger("ltx.session")
        self._requests = []
        self._stop = False
        self._connected = False
        self._stdin_fd = stdin_fd
        self._stdout_fd = stdout_fd
        self._lock = asyncio.Lock()

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

    def _blocking_read(self, size: int) -> bytes:
        """
        Blocking I/O method to read from stdout.
        """
        return os.read(self._stdout_fd, size)

    def _blocking_write(self, data: bytes) -> None:
        """
        Blocking I/O method to write on stdin.
        """
        towrite = len(data)
        wrote = os.write(self._stdin_fd, data)

        if towrite != wrote:
            raise kirk.KirkException(
                f"Wrote {wrote} bytes but expected {towrite}")

    def _feed_requests(self, data: list) -> None:
        """
        Feed the list of requests with given data.
        """
        # TODO: this method could be improved by using producer/consumer
        # pattern and gathering multiple tasks according with the number
        # of requests we have
        pos = 0

        while pos < len(self._requests):
            request = self._requests[pos]
            request.check_error(data)
            request.feed(data)

            if request.completed:
                del self._requests[pos]
            else:
                pos += 1

    def _blocking_producer(self) -> None:
        """
        Blocking I/O producer that reads messages from stdout.
        """
        self._logger.info("Starting message polling")
        self._connected = True

        poller = select.epoll()
        poller.register(self._stdout_fd, select.EPOLLIN)

        # force utf-8 encoding by using raw=False
        unpacker = msgpack.Unpacker(raw=False)

        while not self._stop:
            events = poller.poll(0.1)

            for fdesc, _ in events:
                if fdesc != self._stdout_fd:
                    continue

                data = self._blocking_read(self.BUFFSIZE)
                if not data:
                    continue

                unpacker.feed(data)

                self._logger.debug("Unpacking bytes: %s", data)

                while True:
                    try:
                        msg = unpacker.unpack()
                        if msg:
                            self._logger.info("Received message: %s", msg)
                            self._feed_requests(msg)
                    except msgpack.OutOfData:
                        break

        self._connected = False
        self._logger.info("Ending message polling")

    @property
    def connected(self) -> bool:
        """
        True if connected, False otherwise.
        """
        return self._connected

    async def connect(self) -> None:
        """
        Connect to LTX.
        """
        if self.connected:
            return

        self._logger.info("Connecting to LTX")

        kirk.to_thread(self._blocking_producer)

        while not self.connected:
            await asyncio.sleep(0.01)

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
            await asyncio.sleep(0.01)

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

        with await self._lock:
            self._logger.info("Sending requests")
            self._requests.extend(requests)

            data = [req.pack() for req in requests]
            tosend = b''.join(data)

            self._blocking_write(bytes(tosend))

    async def gather(self, requests: list, timeout: float) -> dict:
        """
        Gather multiple requests and wait for the response, then return all
        rquests' replies inside a dictionary that maps requests with their
        reply. Beware that this coroutine will override "on_complete" event for
        all requests.
        """
        req_len = len(requests)
        replies = {}

        async def wait_for_completed():
            while len(replies) != req_len:
                await asyncio.sleep(1e-3)

        def on_complete(req, *args):
            replies[req] = args

        for req in requests:
            req.on_complete = on_complete

        await asyncio.gather(*[
            self.send(requests),
            asyncio.wait_for(wait_for_completed(), timeout=timeout),
        ])

        return replies


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
        self._env = None
        self._cwd = None
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
        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._stdin = kwargs.get("stdin", None)
        self._stdout = kwargs.get("stdout", None)

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
                requests.append(kill(slot_id))

            if requests:
                await self._ltx.gather(requests, timeout=360)

                while self._slots:
                    await asyncio.sleep(1e-2)

        await self._ltx.disconnect()

        while await self.is_running:
            await asyncio.sleep(1e-2)

        if self._stdin_fd != -1:
            os.close(self._stdin_fd)

        if self._stdout_fd != -1:
            os.close(self._stdout_fd)

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

        req = ping()
        start_t = time.monotonic()
        replies = await self._ltx.gather([req], timeout=1)

        return (replies[req][0] * 1e-9) - start_t

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is already running")

        self._stdin_fd = os.open(self._stdin, os.O_WRONLY)
        self._stdout_fd = os.open(self._stdout, os.O_RDONLY)

        self._ltx = Session(
            self._stdin_fd,
            self._stdout_fd)

        await self._ltx.connect()

        requests = []
        requests.append(version())

        if self._cwd:
            requests.append(cwd(Request.ALL_SLOTS, self._cwd))

        if self._env:
            for key, value in self._env.items():
                requests.append(env(Request.ALL_SLOTS, key, value))

        await self._ltx.gather(requests, timeout=10)

    async def run_command(
            self,
            command: str,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("SUT is not running")

        def _stdout_callback(data):
            if iobuffer:
                kirk.to_thread(iobuffer.write(data))

        self._logger.info("Running command: %s", repr(command))

        slot_id = await self._reserve_slot()
        ret = None

        try:
            start_t = time.monotonic()

            req = execute(
                slot_id,
                command,
                stdout_callback=_stdout_callback)

            replies = await self._ltx.gather([req], timeout=3600)
            reply = replies[req]

            ret = {
                "command": command,
                "stdout": reply[0],
                "exec_time": (reply[1] * 1e-9) - start_t,
                "returncode": reply[3],
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

        if not os.path.isfile(target_path):
            raise SUTError("target path doesn't exist")

        with await self._fetch_lock:
            req = get_file(target_path)
            replies = await self._ltx.gather([req], timeout=3600)
            reply = replies[req]

            return reply[0]
