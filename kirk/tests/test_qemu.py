"""
Test SUT implementations.
"""
import os
import pytest
from kirk.qemu import QemuSUT
from kirk.sut import KernelPanicError
from kirk.tests.sut import _TestSUT
from kirk.tests.sut import Printer

pytestmark = pytest.mark.asyncio

TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)


@pytest.mark.qemu
@pytest.mark.skipif(
    TEST_QEMU_IMAGE is None,
    reason="TEST_QEMU_IMAGE is not defined")
@pytest.mark.skipif(
    TEST_QEMU_PASSWORD is None,
    reason="TEST_QEMU_PASSWORD is not defined")
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


class TestQemuSUTISA(_TestQemuSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    async def sut(self, tmpdir):
        iobuff = Printer()

        runner = QemuSUT()
        runner.setup(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="isa")

        yield runner

        if await runner.is_running:
            await runner.stop(iobuffer=iobuff)


class TestQemuSUTVirtIO(_TestQemuSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    async def sut(self, tmpdir):
        runner = QemuSUT()
        runner.setup(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="virtio")

        yield runner

        if await runner.is_running:
            await runner.stop()
