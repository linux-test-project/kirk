"""
Test GenericSUT implementations.
"""

import asyncio
import logging

import pytest

import libkirk.sut
from libkirk.com import IOBuffer


class Printer(IOBuffer):
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.sut")

    async def write(self, data: str) -> None:
        print(data, end="")


@pytest.fixture
async def sut():
    """
    SUT object to test.
    """
    raise NotImplementedError()


class _TestSUT:
    """
    Unittest for GenericSUT implementations.
    """

    async def test_get_channel(self, sut):
        """
        Test if get_channel() returns a communication channel when SUT has
        been initialized.
        """
        assert sut.get_channel()

    async def test_start(self, sut):
        """
        Test start method.
        """
        await sut.start(iobuffer=Printer())
        assert await sut.is_running()

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Setup sleep time before calling stop after communicate.
        By changing multiply factor it's possible to tweak stop sleep and
        change the behaviour of `test_stop_communicate`.
        """
        return request.param * 1.0

    @pytest.mark.parametrize("sut_stop_sleep", [1, 2], indirect=True)
    async def test_start_stop(self, sut, sut_stop_sleep):
        """
        Test stop method when running start.
        """
        async def stop():
            await asyncio.sleep(sut_stop_sleep)
            await sut.stop(iobuffer=Printer())

        await asyncio.gather(
            *[sut.start(iobuffer=Printer()), stop()], return_exceptions=True
        )

    async def test_config_help(self, sut):
        """
        Test if config_help has the right type.
        """
        assert isinstance(sut.config_help, dict)

    async def test_get_info(self, sut):
        """
        Test get_info method.
        """
        await sut.start(iobuffer=Printer())
        info = await sut.get_info()

        assert info["distro"]
        assert info["distro_ver"]
        assert info["kernel"]
        assert info["cmdline"]
        assert info["arch"]

    async def test_get_tainted_info(self, sut):
        """
        Test get_tainted_info.
        """
        await sut.start(iobuffer=Printer())
        code, messages = await sut.get_tainted_info()

        assert code >= 0
        assert isinstance(messages, list)

    # TODO: test the following
    # - tainted info
    # - fault injection
    # - is root


class MockChannel:
    """
    Mock communication channel for testing SUT methods.
    """

    def __init__(self):
        self._responses = {}

    def set_response(self, cmd, returncode=0, stdout=""):
        self._responses[cmd] = {"returncode": returncode, "stdout": stdout}

    async def run_command(self, command, **kwargs):
        for key, resp in self._responses.items():
            if key in command:
                return resp
        return {"returncode": 0, "stdout": ""}


class MockSUT(libkirk.sut.SUT):
    """
    Mock SUT for testing concrete methods.
    """

    def __init__(self):
        self._channel = MockChannel()
        self._running = True

    @property
    def name(self):
        return "mock"

    def get_channel(self):
        return self._channel

    async def start(self, iobuffer=None):
        self._running = True

    async def stop(self, iobuffer=None):
        self._running = False

    async def restart(self, iobuffer=None):
        self._running = True

    async def is_running(self):
        return self._running


@pytest.fixture
def mock_sut():
    return MockSUT()


async def test_get_info_not_running(mock_sut):
    """
    Test get_info raises when SUT is not running.
    """
    mock_sut._running = False
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.get_info()


async def test_get_info(mock_sut):
    """
    Test get_info returns system information.
    """
    mock_sut._channel.set_response("os-release && echo \"$ID\"", stdout="opensuse\n")
    mock_sut._channel.set_response(
        "os-release && echo \"$VERSION_ID\"", stdout="15.5\n"
    )
    mock_sut._channel.set_response("uname -s -r -v", stdout="Linux 6.1.0\n")
    mock_sut._channel.set_response("cat /proc/cmdline", stdout="root=/dev/sda\n")
    mock_sut._channel.set_response("uname -m", stdout="x86_64\n")
    mock_sut._channel.set_response("uname -p", stdout="x86_64\n")
    mock_sut._channel.set_response(
        "cat /proc/meminfo",
        stdout="MemTotal:       16384 kB\nSwapTotal:       8192 kB\n",
    )

    info = await mock_sut.get_info()
    assert info["distro"] == "opensuse"
    assert info["distro_ver"] == "15.5"
    assert info["kernel"] == "Linux 6.1.0"
    assert info["ram"] == "16384 kB"
    assert info["swap"] == "8192 kB"


async def test_get_info_optimized(mock_sut):
    """
    Test get_info with optimize=True uses asyncio.gather.
    """
    mock_sut.optimize = True
    mock_sut._channel.set_response("os-release && echo \"$ID\"", stdout="fedora\n")
    mock_sut._channel.set_response(
        "os-release && echo \"$VERSION_ID\"", stdout="39\n"
    )
    mock_sut._channel.set_response("uname -s -r -v", stdout="Linux 6.5.0\n")
    mock_sut._channel.set_response("cat /proc/cmdline", stdout="root=/dev/sda\n")
    mock_sut._channel.set_response("uname -m", stdout="x86_64\n")
    mock_sut._channel.set_response("uname -p", stdout="x86_64\n")
    mock_sut._channel.set_response(
        "cat /proc/meminfo",
        stdout="MemTotal:       8192 kB\nSwapTotal:       4096 kB\n",
    )

    info = await mock_sut.get_info()
    assert info["distro"] == "fedora"
    assert info["ram"] == "8192 kB"


async def test_get_tainted_info_not_running(mock_sut):
    """
    Test get_tainted_info raises when SUT is not running.
    """
    mock_sut._running = False
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.get_tainted_info()


async def test_get_tainted_info_clean(mock_sut):
    """
    Test get_tainted_info with clean kernel (tainted=0).
    """
    mock_sut._channel.set_response("cat /proc/sys/kernel/tainted", stdout="0\n")

    code, messages = await mock_sut.get_tainted_info()
    assert code == 0
    assert messages == []


async def test_get_tainted_info_tainted(mock_sut):
    """
    Test get_tainted_info with tainted kernel.
    """
    # bit 0 = "proprietary module was loaded"
    # bit 1 = "module was force loaded"
    mock_sut._channel.set_response("cat /proc/sys/kernel/tainted", stdout="3\n")

    code, messages = await mock_sut.get_tainted_info()
    assert code == 3
    assert len(messages) == 2
    assert "proprietary module was loaded" in messages
    assert "module was force loaded" in messages


async def test_get_tainted_info_error(mock_sut):
    """
    Test get_tainted_info when command fails.
    """
    mock_sut._channel.set_response(
        "cat /proc/sys/kernel/tainted", returncode=1, stdout="error"
    )

    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.get_tainted_info()


async def test_get_tainted_info_non_digit(mock_sut):
    """
    Test get_tainted_info when output is not a digit.
    """
    mock_sut._channel.set_response(
        "cat /proc/sys/kernel/tainted", stdout="Permission denied\n"
    )

    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.get_tainted_info()


async def test_logged_as_root(mock_sut):
    """
    Test logged_as_root returns True when uid is 0.
    """
    mock_sut._channel.set_response("id -u", stdout="0\n")
    assert await mock_sut.logged_as_root()


async def test_logged_as_not_root(mock_sut):
    """
    Test logged_as_root returns False when uid is not 0.
    """
    mock_sut._channel.set_response("id -u", stdout="1000\n")
    assert not await mock_sut.logged_as_root()


async def test_logged_as_root_not_running(mock_sut):
    """
    Test logged_as_root raises when SUT is not running.
    """
    mock_sut._running = False
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.logged_as_root()


async def test_logged_as_root_error(mock_sut):
    """
    Test logged_as_root raises when command fails.
    """
    mock_sut._channel.set_response("id -u", returncode=1, stdout="error")
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.logged_as_root()


async def test_logged_as_root_invalid(mock_sut):
    """
    Test logged_as_root raises when output is not a number.
    """
    mock_sut._channel.set_response("id -u", stdout="not_a_number\n")
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.logged_as_root()


async def test_is_fault_injection_enabled(mock_sut):
    """
    Test is_fault_injection_enabled returns True when all debug dirs exist.
    """
    for f in libkirk.sut.SUT.FAULT_INJECTION_FILES:
        mock_sut._channel.set_response(f"test -d /sys/kernel/debug/{f}", stdout="")

    assert await mock_sut.is_fault_injection_enabled()


async def test_is_fault_injection_disabled(mock_sut):
    """
    Test is_fault_injection_enabled returns False when a debug dir is missing.
    """
    mock_sut._channel.set_response("test -d", returncode=1, stdout="")
    assert not await mock_sut.is_fault_injection_enabled()


async def test_is_fault_injection_not_running(mock_sut):
    """
    Test is_fault_injection_enabled raises when SUT is not running.
    """
    mock_sut._running = False
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.is_fault_injection_enabled()


async def test_redirect_sut_stdout_sut_event():
    """
    Test RedirectSUTStdout fires sut_stdout event.
    """
    import libkirk

    received = []

    async def handler(name, data):
        received.append((name, data))

    libkirk.events.register("sut_stdout", handler)

    async def start():
        await libkirk.events.start()

    libkirk.create_task(start())

    mock = MockSUT()
    redirect = libkirk.sut.RedirectSUTStdout(mock, is_cmd=False)
    await redirect.write("hello")

    while not received:
        await asyncio.sleep(1e-3)

    await libkirk.events.stop()

    assert received[0] == ("mock", "hello")


async def test_redirect_sut_stdout_cmd_event():
    """
    Test RedirectSUTStdout fires run_cmd_stdout event when is_cmd=True.
    """
    import libkirk

    received = []

    async def handler(data):
        received.append(data)

    libkirk.events.register("run_cmd_stdout", handler)

    async def start():
        await libkirk.events.start()

    libkirk.create_task(start())

    mock = MockSUT()
    redirect = libkirk.sut.RedirectSUTStdout(mock, is_cmd=True)
    await redirect.write("cmd output")

    while not received:
        await asyncio.sleep(1e-3)

    await libkirk.events.stop()

    assert received[0] == "cmd output"


async def test_redirect_test_stdout():
    """
    Test RedirectTestStdout fires test_stdout event and captures stdout.
    """
    import libkirk
    from libkirk.data import Test

    received = []

    async def handler(test, data):
        received.append((test, data))

    libkirk.events.register("test_stdout", handler)

    async def start():
        await libkirk.events.start()

    libkirk.create_task(start())

    test = Test(name="mytest", cmd="echo")
    redirect = libkirk.sut.RedirectTestStdout(test)
    await redirect.write("output1")
    await redirect.write("output2")

    while len(received) < 2:
        await asyncio.sleep(1e-3)

    await libkirk.events.stop()

    assert redirect.stdout == "output1output2"
    assert received[0][1] == "output1"
    assert received[1][1] == "output2"


async def test_setup_fault_injection(mock_sut):
    """
    Test setup_fault_injection configures kernel fault injection.
    """
    mock_sut._channel.set_response("echo", stdout="")
    await mock_sut.setup_fault_injection(50)


async def test_setup_fault_injection_reset(mock_sut):
    """
    Test setup_fault_injection with prob=0 resets to defaults.
    """
    mock_sut._channel.set_response("echo", stdout="")
    await mock_sut.setup_fault_injection(0)


async def test_setup_fault_injection_not_running(mock_sut):
    """
    Test setup_fault_injection raises when SUT is not running.
    """
    mock_sut._running = False
    with pytest.raises(libkirk.sut.SUTError):
        await mock_sut.setup_fault_injection(50)


def test_discover(tmpdir):
    """
    Test if SUT implementations are correctly discovered.
    """
    impl = []
    impl.append(tmpdir / "sutA.py")
    impl.append(tmpdir / "sutB.py")
    impl.append(tmpdir / "sutC.txt")

    for index in range(0, len(impl)):
        impl[index].write(
            "from libkirk.sut import SUT\n\n"
            f"class MySUT{index}(SUT):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'sut{index}'\n"
        )

    libkirk.sut.discover(str(tmpdir), extend=False)

    suts = libkirk.sut.get_suts()
    assert len(suts) == 2

    names = [c.name for c in suts]
    assert "sut0" in names
    assert "sut1" in names
