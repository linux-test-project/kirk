"""
Unittests for ltx module.
"""
import os
import time
import signal
import subprocess
import pytest
import libkirk.ltx as ltx
from libkirk.ltx import Requests
from libkirk.ltx import LTXSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.asyncio, pytest.mark.ltx]

TEST_LTX_BINARY = os.environ.get("TEST_LTX_BINARY", None)

if not TEST_LTX_BINARY or not os.path.isfile(TEST_LTX_BINARY):
    pytestmark.append(pytest.mark.skip(
        reason="TEST_LTX_BINARY doesn't exist"))


class TestLTX:
    """
    Unittest for LTX class.
    """

    @pytest.fixture(scope="session")
    async def handle(self):
        """
        LTX session handler.
        """
        with subprocess.Popen(
                TEST_LTX_BINARY,
                bufsize=0,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE) as proc:
            async with ltx.Session(
                    proc.stdin.fileno(),
                    proc.stdout.fileno()) as handle:
                yield handle

    async def test_version(self, handle):
        """
        Test version request.
        """
        req = Requests.version()
        replies = await handle.gather([req], timeout=1)
        assert replies[req][0] == "0.1"

    async def test_ping(self, handle):
        """
        Test ping request.
        """
        start_t = time.monotonic()
        req = Requests.ping()
        replies = await handle.gather([req], timeout=1)
        assert start_t < replies[req][0] * 1e-9 < time.monotonic()

    async def test_ping_flood(self, handle):
        """
        Test multiple ping request in a row.
        """
        times = 100
        requests = []
        for _ in range(times):
            requests.append(Requests.ping())

        start_t = time.monotonic()
        replies = await handle.gather(requests, timeout=10)
        end_t = time.monotonic()

        for reply in replies:
            assert start_t < replies[reply][0] * 1e-9 < end_t

    async def test_execute(self, handle):
        """
        Test execute request.
        """
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        start_t = time.monotonic()
        req = Requests.execute(0, "uname", stdout_callback=_stdout_callback)
        replies = await handle.gather([req], timeout=3)
        reply = replies[req]

        assert ''.join(stdout) == "Linux\n"
        assert reply[0] == "Linux\n"
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_execute_builtin(self, handle):
        """
        Test execute request with builtin command.
        """
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        start_t = time.monotonic()
        req = Requests.execute(
            0, "echo -n ciao", stdout_callback=_stdout_callback)
        replies = await handle.gather([req], timeout=3)
        reply = replies[req]

        assert ''.join(stdout) == "ciao"
        assert reply[0] == "ciao"
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_execute_multiple(self, handle):
        """
        Test multiple execute request in a row.
        """
        times = os.cpu_count()
        stdout = []

        def _stdout_callback(data):
            stdout.append(data)

        start_t = time.monotonic()
        req = []
        for slot in range(times):
            req.append(Requests.execute(slot, "echo -n ciao",
                       stdout_callback=_stdout_callback))

        replies = await handle.gather(req, timeout=3)
        end_t = time.monotonic()

        for reply in replies.values():
            assert reply[0] == "ciao"
            assert start_t < reply[1] * 1e-9 < end_t
            assert reply[2] == 1
            assert reply[3] == 0

        for data in stdout:
            assert data == "ciao"

    async def test_set_file(self, handle, tmp_path):
        """
        Test set_file request.
        """
        data = b'AaXa\x00\x01\x02Zz' * 1024
        pfile = tmp_path / 'file.bin'

        req = Requests.set_file(str(pfile), data)
        await handle.gather([req], timeout=5)

        assert pfile.read_bytes() == data

    async def test_get_file(self, handle, tmp_path):
        """
        Test get_file request.
        """
        pfile = tmp_path / 'file.bin'
        pfile.write_bytes(b'AaXa\x00\x01\x02Zz' * 1024)

        req = Requests.get_file(str(pfile))
        replies = await handle.gather([req], timeout=5)

        assert pfile.read_bytes() == replies[req][0]

    async def test_kill(self, handle):
        """
        Test kill method.
        """
        start_t = time.monotonic()
        exec_req = Requests.execute(0, "sleep 1")
        kill_req = Requests.kill(0)
        replies = await handle.gather([exec_req, kill_req], timeout=3)
        reply = replies[exec_req]

        assert reply[0] == ""
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 2
        assert reply[3] == signal.SIGKILL

    async def test_env(self, handle):
        """
        Test env request.
        """
        start_t = time.monotonic()
        env_req = Requests.env(0, "HELLO", "CIAO")
        exec_req = Requests.execute(0, "echo -n $HELLO")
        replies = await handle.gather([env_req, exec_req], timeout=3)
        reply = replies[exec_req]

        assert reply[0] == "CIAO"
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_env_multiple(self, handle):
        """
        Test env request.
        """
        start_t = time.monotonic()
        env_req = Requests.env(128, "HELLO", "CIAO")
        exec_req = Requests.execute(0, "echo -n $HELLO")
        replies = await handle.gather([env_req, exec_req], timeout=3)
        reply = replies[exec_req]

        assert reply[0] == "CIAO"
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_cwd(self, handle, tmpdir):
        """
        Test cwd request.
        """
        path = str(tmpdir)

        start_t = time.monotonic()
        env_req = Requests.cwd(0, path)
        exec_req = Requests.execute(0, "echo -n $PWD")
        replies = await handle.gather([env_req, exec_req], timeout=3)
        reply = replies[exec_req]

        assert reply[0] == path
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_cwd_multiple(self, handle, tmpdir):
        """
        Test cwd request on multiple slots.
        """
        path = str(tmpdir)

        start_t = time.monotonic()
        env_req = Requests.cwd(128, path)
        exec_req = Requests.execute(0, "echo -n $PWD")
        replies = await handle.gather([env_req, exec_req], timeout=3)
        reply = replies[exec_req]

        assert reply[0] == path
        assert start_t < reply[1] * 1e-9 < time.monotonic()
        assert reply[2] == 1
        assert reply[3] == 0

    async def test_all_together(self, handle, tmp_path):
        """
        Test all requests together.
        """
        data = b'AaXa\x00\x01\x02Zz' * 1024
        pfile = tmp_path / 'file.bin'

        requests = []
        requests.append(Requests.version())
        requests.append(Requests.set_file(str(pfile), data))
        requests.append(Requests.ping())
        requests.append(Requests.env(0, "HELLO", "CIAO"))
        requests.append(Requests.execute(0, "sleep 5"))
        requests.append(Requests.kill(0))
        requests.append(Requests.get_file(str(pfile)))

        await handle.gather(requests, timeout=10)


@pytest.fixture
async def sut(tmpdir):
    """
    LTXSUT instance object.
    """
    stdin_path = str(tmpdir / 'transport.in')
    stdout_path = str(tmpdir / 'transport.out')

    os.mkfifo(stdin_path)
    os.mkfifo(stdout_path)

    stdin = os.open(stdin_path, os.O_RDONLY | os.O_NONBLOCK)
    stdout = os.open(stdout_path, os.O_RDWR)

    proc = subprocess.Popen(
        TEST_LTX_BINARY,
        stdin=stdin,
        stdout=stdout,
        stderr=stdout,
        bufsize=0,
        shell=True)

    sut = LTXSUT()
    sut.setup(
        cwd=str(tmpdir),
        env=dict(HELLO="WORLD"),
        stdin=stdin_path,
        stdout=stdout_path)

    yield sut

    if await sut.is_running:
        await sut.stop()

    proc.kill()


class TestLTXSUT(_TestSUT):
    """
    Test HostSUT implementation.
    """

    async def test_fetch_file_stop(self):
        pytest.skip(reason="LTX doesn't support stop for GET_FILE")


class TestLTXSession(_TestSession):
    """
    Test Session implementation using LTX SUT.
    """
