"""
Unittests for ssh module.
"""
import os
import asyncio
import pytest
from libkirk.sut import IOBuffer
from libkirk.sut import KernelPanicError
from libkirk.ssh import SSHSUT
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.asyncio, pytest.mark.ssh]

TEST_SSH_USERNAME = os.environ.get("TEST_SSH_USERNAME", None)
TEST_SSH_PASSWORD = os.environ.get("TEST_SSH_PASSWORD", None)
TEST_SSH_KEY_FILE = os.environ.get("TEST_SSH_KEY_FILE", None)

if not TEST_SSH_USERNAME:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_SSH_USERNAME not defined"))

if not TEST_SSH_PASSWORD:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_SSH_PASSWORD not defined"))

if not TEST_SSH_KEY_FILE:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_SSH_KEY_FILE not defined"))


@pytest.fixture
def config():
    """
    Base configuration to connect to SUT.
    """
    raise NotImplementedError()


@pytest.fixture
async def sut(config):
    """
    SSH SUT communication object.
    """
    sut = SSHSUT()
    sut.setup(**config)

    yield sut

    if await sut.is_running:
        await sut.stop()


class _TestSSHSUT(_TestSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    async def test_reset_command(self, config):
        """
        Test reset_command option.
        """
        kwargs = dict(reset_cmd="echo ciao")
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        await sut.communicate()

        class MyBuffer(IOBuffer):
            data = ""

            async def write(self, data: str) -> None:
                self.data = data
                # wait for data inside the buffer
                await asyncio.sleep(0.1)

        buffer = MyBuffer()
        await sut.stop(iobuffer=buffer)

        assert buffer.data == 'ciao\n'

    @pytest.mark.parametrize("enable", ["0", "1"])
    async def test_sudo(self, config, enable):
        """
        Test sudo parameter.
        """
        kwargs = dict(sudo=enable)
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        await sut.communicate()
        ret = await sut.run_command("whoami")

        if enable == "1":
            assert ret["stdout"] == "root\n"
        else:
            assert ret["stdout"] != "root\n"

    async def test_kernel_panic(self, sut):
        """
        Test kernel panic recognition.
        """
        await sut.communicate()

        with pytest.raises(KernelPanicError):
            await sut.run_command(
                "echo 'Kernel panic\nThis is a generic message'")


@pytest.fixture
def config_password(tmpdir):
    """
    SSH configuration to use user/password.
    """
    return dict(
        tmpdir=str(tmpdir),
        host="localhost",
        port=22,
        user=TEST_SSH_USERNAME,
        password=TEST_SSH_PASSWORD)


@pytest.fixture
def config_keyfile(tmpdir):
    """
    SSH configuration to use keyfile.
    """
    return dict(
        tmpdir=str(tmpdir),
        host="localhost",
        port=22,
        user=TEST_SSH_USERNAME,
        key_file=TEST_SSH_KEY_FILE)


class TestSSHSUTPassword(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, config_password):
        yield config_password


class TestSSHSUTKeyfile(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, config_keyfile):
        yield config_keyfile


class TestSessionSSHPassword(_TestSession):
    """
    Test Session implementation using SSH SUT in password mode.
    """

    @pytest.fixture
    def config(self, config_password):
        yield config_password


class TestSessionSSHKeyfile(_TestSession):
    """
    Test Session implementation using SSH SUT in keyfile mode.
    """

    @pytest.fixture
    def config(self, config_keyfile):
        yield config_keyfile
