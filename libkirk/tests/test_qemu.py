"""
Test SUT implementations.
"""
import os
import pytest
from libkirk.qemu import QemuSUT
from libkirk.sut import KernelPanicError
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_sut import Printer
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.asyncio, pytest.mark.qemu]

TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_USERNAME = os.environ.get("TEST_QEMU_USERNAME", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)
TEST_QEMU_KERNEL = os.environ.get("TEST_QEMU_KERNEL", None)
TEST_QEMU_BUSYBOX = os.environ.get("TEST_QEMU_BUSYBOX", None)

if not TEST_QEMU_IMAGE:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_QEMU_IMAGE not defined"))

if not TEST_QEMU_USERNAME:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_QEMU_USERNAME not defined"))

if not TEST_QEMU_PASSWORD:
    pytestmark.append(pytest.mark.skip(
        reason="TEST_QEMU_PASSWORD not defined"))


class _TestQemuSUT(_TestSUT):
    """
    Test Qemu SUT implementation.
    """

    async def test_kernel_panic(self, sut):
        """
        Test kernel panic recognition.
        """
        iobuff = Printer()

        await sut.communicate(iobuffer=iobuff)
        await sut.run_command(
            "echo 'Kernel panic\nThis is a generic message' > /tmp/panic.txt",
            iobuffer=iobuff)

        with pytest.raises(KernelPanicError):
            await sut.run_command(
                "cat /tmp/panic.txt",
                iobuffer=iobuff)

    async def test_fetch_file_stop(self):
        pytest.skip(reason="Coroutines don't support I/O file handling")


@pytest.fixture
async def sut_isa(tmpdir):
    """
    Qemu instance using ISA.
    """
    iobuff = Printer()

    runner = QemuSUT()
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="isa")

    yield runner

    if await runner.is_running:
        await runner.stop(iobuffer=iobuff)


@pytest.fixture
async def sut_virtio(tmpdir):
    """
    Qemu instance using VirtIO.
    """
    runner = QemuSUT()
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="virtio")

    yield runner

    if await runner.is_running:
        await runner.stop()


class TestQemuSUTISA(_TestQemuSUT):
    """
    Test QemuSUT implementation using ISA protocol.
    """

    @pytest.fixture
    async def sut(self, sut_isa):
        yield sut_isa


class TestQemuSUTVirtIO(_TestQemuSUT):
    """
    Test QemuSUT implementation using VirtIO protocol.
    """

    @pytest.fixture
    async def sut(self, sut_virtio):
        yield sut_virtio


class TestSessionQemuISA(_TestSession):
    """
    Test Session using Qemu with ISA protocol.
    """

    @pytest.fixture
    async def sut(self, sut_isa):
        yield sut_isa


class TestSessionQemuVirtIO(_TestSession):
    """
    Test Session using Qemu with ISA protocol.
    """

    @pytest.fixture
    async def sut(self, sut_virtio):
        yield sut_virtio


@pytest.mark.skipif(
    not TEST_QEMU_KERNEL,
    reason="TEST_QEMU_KERNEL not defined")
@pytest.mark.skipif(
    not TEST_QEMU_BUSYBOX,
    reason="TEST_QEMU_BUSYBOX not defined")
class TestQemuSUTBusybox(_TestQemuSUT):
    """
    Test QemuSUT implementation using kernel/initrd functionality with
    busybox initramfs image.
    """

    @pytest.fixture
    async def sut(self, tmpdir):
        """
        Qemu instance using kernel/initrd.
        """
        runner = QemuSUT()
        runner.setup(
            tmpdir=str(tmpdir),
            kernel=TEST_QEMU_KERNEL,
            initrd=TEST_QEMU_BUSYBOX,
            prompt="/ #")

        yield runner

        if await runner.is_running:
            await runner.stop()
