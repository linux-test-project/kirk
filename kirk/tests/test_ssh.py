"""
Unittests for ssh module.
"""
import os
import asyncio
import pytest
from kirk.sut import IOBuffer
from kirk.sut import KernelPanicError
from kirk.ssh import SSHSUT
from kirk.tests.sut import _TestSUT

pytestmark = pytest.mark.asyncio


TEST_SSH_USERNAME = os.environ.get("TEST_SSH_USERNAME", None)
TEST_SSH_PASSWORD = os.environ.get("TEST_SSH_PASSWORD", None)
TEST_SSH_KEY_FILE = os.environ.get("TEST_SSH_KEY_FILE", None)


@pytest.mark.ssh
class _TestSSHSUT(_TestSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self):
        """
        Base configuration to connect to SUT.
        """
        raise NotImplementedError()

    @pytest.fixture
    async def sut(self, config):
        sut = SSHSUT()
        sut.setup(**config)

        yield sut

        if await sut.is_running:
            await sut.stop()

    async def test_cwd(self, config):
        """
        Test CWD constructor argument.
        """
        kwargs = dict(cwd="/etc")
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        await sut.communicate()

        ret = await sut.run_command("test -f fstab")
        assert ret["returncode"] == 0

    async def test_env(self, config):
        """
        Test ENV constructor argument.
        """
        kwargs = dict(env=dict(BOOOOOH="myfile"))
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        await sut.communicate()

        ret = await sut.run_command("echo -n $BOOOOOH")
        assert ret["returncode"] == 0
        assert ret["stdout"] == "myfile"

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


@pytest.mark.skipif(
    TEST_SSH_USERNAME is None,
    reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(
    TEST_SSH_PASSWORD is None,
    reason="TEST_SSH_PASSWORD is not defined")
class TestSSHSUTPassword(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, tmpdir):
        return dict(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            password=TEST_SSH_PASSWORD)


@pytest.mark.skipif(
    TEST_SSH_USERNAME is None,
    reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(
    TEST_SSH_KEY_FILE is None,
    reason="TEST_SSH_KEY_FILE is not defined")
class TestSSHSUTKeyfile(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, tmpdir):
        return dict(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            key_file=TEST_SSH_KEY_FILE)
