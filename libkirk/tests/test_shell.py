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

    async def test_fetch_file_stop(self, com, target_tmpdir=None):
        pytest.skip(reason="Coroutines don't support I/O file handling")

    async def test_run_command_big_output(self, com):
        """
        Test that the whole output is read when the command exits
        before its output has been consumed.
        """
        await com.communicate()

        size = 100000
        for _ in range(10):
            ret = await com.run_command(f"head -c {size} /dev/zero | tr '\\0' x")
            assert ret["returncode"] == 0
            assert ret["stdout"] == "x" * size

    async def test_run_command_background_child(self, com):
        """
        Test that a background child holding the pipe open doesn't
        block the command.
        """
        await com.communicate()

        ret = await com.run_command("echo start; (sleep 1; echo late; sleep 30) &")
        assert ret["returncode"] == 0
        assert ret["stdout"].startswith("start")
        assert ret["exec_time"] < 10


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
