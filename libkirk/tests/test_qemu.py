"""
Unittest for QemuComChannel.
"""

import os

import pytest

import libkirk.com
from libkirk.sut_base import GenericSUT
from libkirk.errors import KernelPanicError
from libkirk.channels.qemu import QemuComChannel
from libkirk.tests.test_com import Printer, _TestComChannel
from libkirk.tests.test_sut import _TestSUT

pytestmark = [pytest.mark.asyncio, pytest.mark.qemu]

TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_USERNAME = os.environ.get("TEST_QEMU_USERNAME", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)
TEST_QEMU_KERNEL = os.environ.get("TEST_QEMU_KERNEL", None)
TEST_QEMU_BUSYBOX = os.environ.get("TEST_QEMU_BUSYBOX", None)

if not TEST_QEMU_IMAGE:
    pytestmark.append(pytest.mark.skip(reason="TEST_QEMU_IMAGE not defined"))

if not TEST_QEMU_USERNAME:
    pytestmark.append(pytest.mark.skip(reason="TEST_QEMU_USERNAME not defined"))

if not TEST_QEMU_PASSWORD:
    pytestmark.append(pytest.mark.skip(reason="TEST_QEMU_PASSWORD not defined"))


class _TestQemuComChannel(_TestComChannel):
    """
    Test QemuComChannel implementation.
    """

    async def test_kernel_panic(self, com):
        """
        Test kernel panic recognition.
        """
        iobuff = Printer()

        await com.communicate(iobuffer=iobuff)
        await com.run_command(
            "echo 'Kernel panic\nThis is a generic message' > /tmp/panic.txt",
            iobuffer=iobuff,
        )

        with pytest.raises(KernelPanicError):
            await com.run_command("cat /tmp/panic.txt", iobuffer=iobuff)

    async def test_fetch_file_stop(self):
        pytest.skip(reason="Coroutines don't support I/O file handling")


@pytest.fixture
async def com_isa(tmpdir):
    """
    Qemu instance using ISA.
    """
    iobuff = Printer()

    runner = next((c for c in libkirk.com.get_channels() if c.name == "qemu"), None)
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="isa",
    )

    yield runner

    if await runner.active:
        await runner.stop(iobuffer=iobuff)


@pytest.fixture
async def com_virtio(tmpdir):
    """
    Qemu instance using VirtIO.
    """
    runner = next((c for c in libkirk.com.get_channels() if c.name == "qemu"), None)
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="virtio",
    )

    yield runner

    if await runner.active:
        await runner.stop()


class TestQemuComChannelISA(_TestQemuComChannel):
    """
    Test QemuComChannel implementation using ISA protocol.
    """

    @pytest.fixture
    async def com(self, com_isa):
        yield com_isa


class TestQemuComChannelVirtIO(_TestQemuComChannel):
    """
    Test QemuComChannel implementation using VirtIO protocol.
    """

    @pytest.fixture
    async def com(self, com_virtio):
        yield com_virtio


@pytest.mark.skipif(not TEST_QEMU_KERNEL, reason="TEST_QEMU_KERNEL not defined")
@pytest.mark.skipif(not TEST_QEMU_BUSYBOX, reason="TEST_QEMU_BUSYBOX not defined")
class TestQemuComChannelBusybox(_TestQemuComChannel):
    """
    Test QemuComChannel implementation using kernel/initrd functionality with
    busybox initramfs image.
    """

    @pytest.fixture
    async def com(self, tmpdir):
        """
        Qemu instance using kernel/initrd.
        """
        runner = QemuComChannel()
        runner.setup(
            tmpdir=str(tmpdir),
            kernel=TEST_QEMU_KERNEL,
            initrd=TEST_QEMU_BUSYBOX,
            prompt="/ #",
        )

        yield runner

        if await runner.active:
            await runner.stop()


class TestSUTQemu(_TestSUT):
    """
    Test GenericSUT using Qemu support. We don't need varius supports, because
    we are only testing SUT API.
    """
    @pytest.fixture
    async def com(self, com_isa):
        yield com_isa

    @pytest.fixture
    async def sut(self, com):
        obj = GenericSUT()
        obj.setup(com="qemu")

        yield obj

        if await obj.is_running:
            await obj.stop()
