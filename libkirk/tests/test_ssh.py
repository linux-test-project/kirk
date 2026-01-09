"""
Unittests for SSHComChannel.
"""

import asyncio
import os
import subprocess

import pytest

import libkirk.com
from libkirk.errors import KernelPanicError
from libkirk.channels.ssh import SSHComChannel
from libkirk.com import IOBuffer
from libkirk.sut_base import GenericSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_com import _TestComChannel
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.ssh]

TEST_SSH_USERNAME = os.environ.get("TEST_SSH_USERNAME", None)
TEST_SSH_PASSWORD = os.environ.get("TEST_SSH_PASSWORD", None)
TEST_SSH_KEY_FILE = os.environ.get("TEST_SSH_KEY_FILE", None)
TEST_SSH_PORT = os.environ.get("TEST_SSH_PORT", "22")

if not TEST_SSH_USERNAME:
    pytestmark.append(pytest.mark.skip(reason="TEST_SSH_USERNAME not defined"))

if not TEST_SSH_PASSWORD:
    pytestmark.append(pytest.mark.skip(reason="TEST_SSH_PASSWORD not defined"))

if not TEST_SSH_KEY_FILE:
    pytestmark.append(pytest.mark.skip(reason="TEST_SSH_KEY_FILE not defined"))


@pytest.fixture
def config():
    """
    Base configuration to connect to ComChannel.
    """
    raise NotImplementedError()


@pytest.fixture
async def com(config):
    """
    SSH communication object.
    """
    obj = SSHComChannel()
    obj = next((c for c in libkirk.com.get_channels() if c.name == "ssh"), None)
    obj.setup(**config)

    yield obj

    if await obj.active:
        await obj.stop()


class _TestSSHComChannel(_TestComChannel):
    """
    Test SSHComChannel implementation using username/password.
    """

    async def test_reset_cmd(self, config):
        """
        Test reset_cmd option.
        """
        kwargs = dict(reset_cmd="echo ciao")
        kwargs.update(config)

        com = SSHComChannel()
        com.setup(**kwargs)
        await com.communicate()

        class MyBuffer(IOBuffer):
            data = ""

            async def write(self, data: str) -> None:
                self.data = data
                # wait for data inside the buffer
                await asyncio.sleep(0.1)

        buffer = MyBuffer()
        await com.stop(iobuffer=buffer)

        assert buffer.data == "ciao\n"

    @pytest.mark.parametrize("enable", ["0", "1"])
    async def test_sudo(self, config, enable):
        """
        Test sudo parameter.
        """
        kwargs = dict(sudo=enable)
        kwargs.update(config)

        com = SSHComChannel()
        com.setup(**kwargs)
        await com.communicate()
        ret = await com.run_command("whoami")

        if enable == "1":
            assert ret["stdout"] == "root\n"
        else:
            assert ret["stdout"] != "root\n"

    async def test_kernel_panic(self, com):
        """
        Test kernel panic recognition.
        """
        await com.communicate()

        with pytest.raises(KernelPanicError):
            await com.run_command("echo 'Kernel panic\nThis is a generic message'")

    async def test_stderr(self, com):
        """
        Test if we are correctly reading stderr.
        """
        await com.communicate()

        ret = await com.run_command(">&2 echo ciao_stderr && echo ciao_stdout")
        assert "ciao_stdout" in ret["stdout"]
        assert "ciao_stderr" in ret["stdout"]

    async def test_long_stdout(self, com):
        """
        Test really long stdout.
        """
        await com.communicate()

        result = subprocess.run(
            "tr -dc 'a-zA-Z0-9' </dev/urandom | head -c 10000",
            shell=True,
            capture_output=True,
            text=True,
            check=True,
        )

        ret = await com.run_command(f"echo -n {result.stdout}")
        assert ret["stdout"] == result.stdout


@pytest.fixture
def config_password(tmpdir):
    """
    SSH configuration to use user/password.
    """
    return dict(
        tmpdir=str(tmpdir),
        host="localhost",
        port=TEST_SSH_PORT,
        user=TEST_SSH_USERNAME,
        password=TEST_SSH_PASSWORD,
    )


@pytest.fixture
def config_keyfile(tmpdir):
    """
    SSH configuration to use keyfile.
    """
    return dict(
        tmpdir=str(tmpdir),
        host="localhost",
        port=TEST_SSH_PORT,
        user=TEST_SSH_USERNAME,
        key_file=TEST_SSH_KEY_FILE,
    )


class TestSSHComChannelPassword(_TestSSHComChannel):
    """
    Test SSHComChannel implementation using username/password.
    """

    @pytest.fixture
    def config(self, config_password):
        yield config_password


class TestSSHComChannelKeyfile(_TestSSHComChannel):
    """
    Test SSHComChannel implementation using keyfile.
    """

    @pytest.fixture
    def config(self, config_keyfile):
        yield config_keyfile


@pytest.fixture
async def sut(com):
    """
    SUT object to test.
    """
    obj = GenericSUT()
    obj.setup(com="ssh")

    yield obj

    if await obj.is_running:
        await obj.stop()


class TestSUTSSHComChannelPassword(_TestSUT):
    """
    Test SSHComChannel implementation using username/password in within SUT.
    """

    @pytest.fixture
    def config(self, config_password):
        yield config_password


class TestSUTSSHComChannelKeyfile(_TestSUT):
    """
    Test SSHComChannel implementation using keyfile in within SUT.
    """

    @pytest.fixture
    def config(self, config_keyfile):
        yield config_keyfile


class TestSessionSSHComChannelPassword(_TestSession):
    """
    Test SSHComChannel implementation using username/password in within Session.
    """

    @pytest.fixture
    def config(self, config_password):
        yield config_password


class TestSessionSSHComChannelKeyfile(_TestSession):
    """
    Test SSHComChannel implementation using keyfile in within Session.
    """

    @pytest.fixture
    def config(self, config_keyfile):
        yield config_keyfile
