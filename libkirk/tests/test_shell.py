"""
Unittests for ShellComChannel.
"""

import pytest

from libkirk.channels.shell import ShellComChannel
from libkirk.tests.test_com import _TestComChannel

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def com():
    obj = ShellComChannel()
    obj.setup()

    yield obj

    if await obj.active:
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
