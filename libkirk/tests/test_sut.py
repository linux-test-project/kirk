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
