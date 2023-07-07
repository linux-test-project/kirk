"""
Unittests for ltx module.
"""
import os
import time
import signal
import asyncio.subprocess
import pytest
from libkirk.ltx import LTX
from libkirk.ltx import Requests
from libkirk.ltx_sut import LTXSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.asyncio, pytest.mark.ltx]

TEST_LTX_BINARY = os.environ.get("TEST_LTX_BINARY", None)

if not TEST_LTX_BINARY or not os.path.isfile(TEST_LTX_BINARY):
    pytestmark.append(pytest.mark.skip(
        reason="TEST_LTX_BINARY doesn't exist"))


class TestLTX:
    """
    Test LTX implementation.
    """

    @pytest.fixture
    async def ltx(self, tmpdir):
        """
        LTX handler.
        """
        stdin_path = str(tmpdir / 'transport.in')
        stdout_path = str(tmpdir / 'transport.out')

        os.mkfifo(stdin_path)
        os.mkfifo(stdout_path)

        stdin = os.open(stdin_path, os.O_RDWR | os.O_NONBLOCK)
        stdout = os.open(stdout_path, os.O_RDWR)

        proc = await asyncio.subprocess.create_subprocess_shell(
            TEST_LTX_BINARY,
            stdin=stdin,
            stdout=stdout)

        try:
            async with LTX(stdin, stdout) as handle:
                yield handle
        finally:
            proc.kill()

    async def test_version(self, ltx):
        """
        Test version request.
        """
        req = Requests.version()
        replies = await ltx.gather([req])
        assert replies[req][0] == "0.1"

    async def test_ping(self, ltx):
        """
        Test ping request.
        """
        start_t = time.monotonic()
        req = Requests.ping()
        replies = await ltx.gather([req])
        assert start_t < replies[req][0] * 1e-9 < time.monotonic()

    async def test_execute(self, ltx):
        """
        Test execute request.
        """
        stdout = []

        async def _stdout_coro(data):
            stdout.append(data)

        start_t = time.monotonic()
        req = Requests.execute(0, "uname", stdout_coro=_stdout_coro)
        replies = await ltx.gather([req])
        reply = replies[req]

        assert ''.join(stdout) == "Linux\n"
        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == "Linux\n"

    async def test_execute_builtin(self, ltx):
        """
        Test execute request with builtin command.
        """
        stdout = []

        async def _stdout_coro(data):
            stdout.append(data)

        start_t = time.monotonic()
        req = Requests.execute(
            0, "echo -n ciao", stdout_coro=_stdout_coro)
        replies = await ltx.gather([req])
        reply = replies[req]

        assert ''.join(stdout) == "ciao"
        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == "ciao"

    async def test_execute_multiple(self, ltx):
        """
        Test multiple execute request in a row.
        """
        times = 2
        stdout = []

        async def _stdout_coro(data):
            stdout.append(data)

        req = []
        for slot in range(times):
            req.append(Requests.execute(
                slot,
                "echo -n ciao",
                stdout_coro=_stdout_coro))

        start_t = time.monotonic()
        replies = await ltx.gather(req)
        end_t = time.monotonic()

        for reply in replies.values():
            assert start_t < reply[0] * 1e-9 < end_t
            assert reply[1] == 1
            assert reply[2] == 0
            assert reply[3] == "ciao"

        for data in stdout:
            assert data == "ciao"

    async def test_set_file(self, ltx, tmp_path):
        """
        Test set_file request.
        """
        data = b'AaXa\x00\x01\x02Zz' * 1024
        pfile = tmp_path / 'file.bin'

        req = Requests.set_file(str(pfile), data)
        await ltx.gather([req])

        assert pfile.read_bytes() == data

    async def test_get_file(self, ltx, tmp_path):
        """
        Test get_file request.
        """
        pfile = tmp_path / 'file.bin'
        pfile.write_bytes(b'AaXa\x00\x01\x02Zz' * 1024)

        req = Requests.get_file(str(pfile))
        replies = await ltx.gather([req])

        assert replies[req][0] == str(pfile)
        assert pfile.read_bytes() == replies[req][1]

    async def test_kill(self, ltx):
        """
        Test kill method.
        """
        start_t = time.monotonic()
        exec_req = Requests.execute(0, "sleep 1")
        kill_req = Requests.kill(0)
        replies = await ltx.gather([exec_req, kill_req])
        reply = replies[exec_req]

        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 2
        assert reply[2] == signal.SIGKILL
        assert reply[3] == ""

    async def test_env(self, ltx):
        """
        Test env request.
        """
        start_t = time.monotonic()
        env_req = Requests.env(0, "HELLO", "CIAO")
        exec_req = Requests.execute(0, "echo -n $HELLO")
        replies = await ltx.gather([env_req, exec_req])
        reply = replies[exec_req]

        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == "CIAO"

    async def test_env_multiple(self, ltx):
        """
        Test env request.
        """
        start_t = time.monotonic()
        env_req = Requests.env(128, "HELLO", "CIAO")
        exec_req = Requests.execute(0, "echo -n $HELLO")
        replies = await ltx.gather([env_req, exec_req])
        reply = replies[exec_req]

        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == "CIAO"

    async def test_cwd(self, ltx, tmpdir):
        """
        Test cwd request.
        """
        path = str(tmpdir)

        start_t = time.monotonic()
        env_req = Requests.cwd(0, path)
        exec_req = Requests.execute(0, "echo -n $PWD")
        replies = await ltx.gather([env_req, exec_req])
        reply = replies[exec_req]

        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == path

    async def test_cwd_multiple(self, ltx, tmpdir):
        """
        Test cwd request on multiple slots.
        """
        path = str(tmpdir)

        start_t = time.monotonic()
        env_req = Requests.cwd(128, path)
        exec_req = Requests.execute(0, "echo -n $PWD")
        replies = await ltx.gather([env_req, exec_req])
        reply = replies[exec_req]

        assert start_t < reply[0] * 1e-9 < time.monotonic()
        assert reply[1] == 1
        assert reply[2] == 0
        assert reply[3] == path

    async def test_all_together(self, ltx, tmp_path):
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

        await ltx.gather(requests)


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

    proc = await asyncio.subprocess.create_subprocess_shell(
        TEST_LTX_BINARY,
        stdin=stdin,
        stdout=stdout)

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
