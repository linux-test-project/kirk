"""
Unittest for QemuComChannel.
"""

import asyncio
import os

import pytest

import libkirk.com
from libkirk.sut_base import GenericSUT
from libkirk.errors import KernelPanicError
from libkirk.channels.qemu import QemuComChannel
from libkirk.tests.test_com import Printer, _TestComChannel
from libkirk.tests.test_sut import _TestSUT
from libkirk.tests.test_session import _TestSession

pytestmark = [pytest.mark.qemu]

TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_USERNAME = os.environ.get("TEST_QEMU_USERNAME", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)
TEST_QEMU_KERNEL = os.environ.get("TEST_QEMU_KERNEL", None)
TEST_QEMU_BUSYBOX = os.environ.get("TEST_QEMU_BUSYBOX", None)

SKIP_IMAGE = not (TEST_QEMU_IMAGE and TEST_QEMU_USERNAME and TEST_QEMU_PASSWORD)
SKIP_BUSYBOX = not (TEST_QEMU_KERNEL and TEST_QEMU_BUSYBOX)

if SKIP_IMAGE and SKIP_BUSYBOX:
    pytestmark.append(
        pytest.mark.skip(reason="Neither QEMU image nor kernel/busybox defined")
    )


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

    async def test_fetch_file_stop(self, com, target_tmpdir=None):
        pytest.skip(reason="Coroutines don't support I/O file handling")

    async def test_cancelled_command_resync(self, com):
        """
        Cancelling an in-flight command must resynchronize the serial line
        so subsequent commands do not read leftover markers or corrupted output.
        """
        iobuff = Printer()
        await com.communicate(iobuffer=iobuff)

        # Start a slow command and cancel it via wait_for timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(com.run_command("sleep 10"), timeout=0.5)

        # The next command must execute cleanly and return its own output
        ret = await com.run_command("echo hello_clean_output", iobuffer=iobuff)
        assert ret is not None
        assert ret["returncode"] == 0
        assert "hello_clean_output" in ret["stdout"]

    async def test_concurrent_console_access_serialized(self, com):
        """
        Concurrent console calls (e.g. ping and run_command) must be serialized
        by _cmd_lock and not collide on stdout.read().
        """
        iobuff = Printer()
        await com.communicate(iobuffer=iobuff)

        # Gather ping and run_command concurrently
        results = await asyncio.gather(
            com.ping(),
            com.run_command("echo serialized", iobuffer=iobuff),
        )
        ping_time, cmd_ret = results
        assert ping_time >= 0
        assert cmd_ret["returncode"] == 0
        assert "serialized" in cmd_ret["stdout"]




@pytest.fixture
async def com_isa(tmpdir):
    """
    Qemu instance using ISA.
    """
    iobuff = Printer()

    runner = next((c for c in libkirk.com.get_channels() if c.name == "qemu"), None)
    assert runner is not None
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="isa",
    )

    yield runner

    if await runner.active():
        await runner.stop(iobuffer=iobuff)


@pytest.fixture
async def com_virtio(tmpdir):
    """
    Qemu instance using VirtIO.
    """
    runner = next((c for c in libkirk.com.get_channels() if c.name == "qemu"), None)
    assert runner is not None
    runner.setup(
        tmpdir=str(tmpdir),
        image=TEST_QEMU_IMAGE,
        user=TEST_QEMU_USERNAME,
        password=TEST_QEMU_PASSWORD,
        serial="virtio",
    )

    yield runner

    if await runner.active():
        await runner.stop()


@pytest.mark.skipif(SKIP_IMAGE, reason="TEST_QEMU_IMAGE config not defined")
class TestQemuComChannelISA(_TestQemuComChannel):
    """
    Test QemuComChannel implementation using ISA protocol.
    """

    @pytest.fixture
    async def com(self, com_isa):
        yield com_isa


@pytest.mark.skipif(SKIP_IMAGE, reason="TEST_QEMU_IMAGE config not defined")
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
        assert TEST_QEMU_KERNEL is not None
        assert TEST_QEMU_BUSYBOX is not None
        runner = QemuComChannel()
        runner.setup(
            tmpdir=str(tmpdir),
            kernel=TEST_QEMU_KERNEL,
            initrd=TEST_QEMU_BUSYBOX,
            prompt="/ #",
        )

        yield runner

        if await runner.active():
            await runner.stop()


@pytest.fixture
async def sut(com_isa):
    obj = GenericSUT()
    obj.setup(com="qemu")

    yield obj

    if await obj.is_running():
        await obj.stop()


@pytest.mark.skipif(SKIP_IMAGE, reason="TEST_QEMU_IMAGE config not defined")
class TestSUTQemu(_TestSUT):
    """
    Test GenericSUT using Qemu support. We don't need varius supports, because
    we are only testing SUT API.
    """


@pytest.mark.skipif(SKIP_IMAGE, reason="TEST_QEMU_IMAGE config not defined")
class TestSessionQemu(_TestSession):
    """
    Test Session using QemuComChannel.
    """
