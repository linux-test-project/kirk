"""
Unittests for ShellComChannel.
"""

import pytest

from libkirk.sut_base import GenericSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession
from libkirk.channels.shell import ShellComChannel
from libkirk.tests.test_com import _TestComChannel


@pytest.fixture
async def com():
    obj = ShellComChannel()
    obj.setup()

    yield obj

    if await obj.active():
        await obj.stop()


class TestShellComChannel(_TestComChannel):
    """
    Test ShellComChannel implementation.
    """

    @pytest.fixture
    def com_stop_sleep(self, request):
        """
        ShellComChannel test doesn't require time sleep in
        `test_stop_communicate`.
        """
        return request.param * 0

    async def test_fetch_file_stop(self):
        pytest.skip(reason="Coroutines don't support I/O file handling")


@pytest.fixture
async def sut(com):
    """
    SUT object to test.
    """
    obj = GenericSUT()
    obj.setup(com="shell")

    yield obj

    if await obj.is_running():
        await obj.stop()


class TestSUTShellComChannel(_TestSUT):
    """
    Test GenericSUT using ShellComChannel.
    """


class TestSessionShellComChannel(_TestSession):
    """
    Test Session using ShellComChannel.
    """
