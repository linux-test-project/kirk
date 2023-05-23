"""
Unittests for host SUT implementations.
"""
import pytest
from libkirk.host import HostSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sut():
    sut = HostSUT()
    sut.setup()

    yield sut

    if await sut.is_running:
        await sut.stop()


class TestHostSUT(_TestSUT):
    """
    Test HostSUT implementation.
    """

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Host SUT test doesn't require time sleep in `test_stop_communicate`.
        """
        return request.param * 0

    async def test_fetch_file_stop(self):
        pytest.skip(reason="Coroutines don't support I/O file handling")


class TestHostSession(_TestSession):
    """
    Test Session implementation.
    """
