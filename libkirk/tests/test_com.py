"""
Test ComChannel implementations.
"""

import asyncio
import logging
import os
import shlex
import time

import pytest

import libkirk
from libkirk.errors import CommunicationError, PluginError
from libkirk.com import IOBuffer


class Printer(IOBuffer):
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.shell")

    async def write(self, data: str) -> None:
        print(data, end="")


class CommandOutput(IOBuffer):
    """
    Capture command output and signal when the target reports readiness.
    """

    def __init__(self):
        self.started = asyncio.Event()
        self.stdout = ""

    async def write(self, data: str) -> None:
        self.stdout += data
        if "ready\n" in self.stdout:
            self.started.set()


@pytest.fixture
def com():
    """
    Expose the ComChannel implementation via this fixture in order to test it.
    """
    raise NotImplementedError()


class _TestComChannel:
    """
    Generic tests for ComChannel implementation.
    """

    _logger = logging.getLogger("test.channel")

    async def test_ping_no_active(self, com):
        """
        Test ping method with no active connection.
        """
        with pytest.raises(CommunicationError):
            await com.ping()

    async def test_ping(self, com):
        """
        Test ping method.
        """
        await com.communicate(iobuffer=Printer())
        ping_t = await com.ping()
        assert ping_t > 0

    async def test_config_help(self, com):
        """
        Test if config_help has the right type.
        """
        assert isinstance(com.config_help, dict)

    async def test_communicate(self, com):
        """
        Test communicate method.
        """
        await com.communicate(iobuffer=Printer())
        with pytest.raises(CommunicationError):
            await com.communicate(iobuffer=Printer())

    async def test_ensure_communicate(self, com):
        """
        Test ensure_communicate method.
        """
        await com.ensure_communicate(iobuffer=Printer())
        with pytest.raises(CommunicationError):
            await com.ensure_communicate(iobuffer=Printer(), retries=1)

    async def test_communicate_stop(self, com):
        """
        Test repeated connection and shutdown after startup completes.
        """
        for _ in range(2):
            await asyncio.wait_for(com.communicate(iobuffer=Printer()), timeout=30)
            assert await com.active()
            await asyncio.wait_for(com.stop(iobuffer=Printer()), timeout=30)
            assert not await com.active()

    async def test_run_command(self, com):
        """
        Execute run_command once.
        """
        await com.communicate(iobuffer=Printer())
        res = await com.run_command("echo 0")

        assert res["returncode"] == 0
        assert int(res["stdout"]) == 0
        assert 0 < res["exec_time"] < time.time()

    async def test_run_command_stop(self, com):
        """
        Execute run_command once, then call stop().
        """
        await com.communicate(iobuffer=Printer())

        output = CommandOutput()

        async def stop():
            await output.started.wait()
            await com.stop(iobuffer=Printer())

        tasks = [
            libkirk.create_task(
                com.run_command("echo ready; exec sleep 60", iobuffer=output)
            ),
            libkirk.create_task(stop()),
        ]
        try:
            res, _ = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
            assert res["returncode"] != 0
            assert res["stdout"] == "ready\n"
            assert not await com.active()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_run_command_parallel(self, com):
        """
        Execute run_command in parallel.
        """
        if not com.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await com.communicate(iobuffer=Printer())

        exec_count = 4
        coros = [com.run_command(f"echo {i}") for i in range(exec_count)]

        results = await asyncio.gather(*coros)

        assert [int(data["stdout"]) for data in results] == list(range(exec_count))
        for data in results:
            assert data["returncode"] == 0
            assert 0 < data["exec_time"] < time.time()

    async def test_run_command_stop_parallel(self, com):
        """
        Execute multiple run_command in parallel, then call stop().
        """
        if not com.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await com.communicate(iobuffer=Printer())

        outputs = [CommandOutput() for _ in range(4)]

        async def stop():
            await asyncio.gather(*(output.started.wait() for output in outputs))
            await com.stop(iobuffer=Printer())

        tasks = [
            libkirk.create_task(
                com.run_command("echo ready; exec sleep 60", iobuffer=output)
            )
            for output in outputs
        ]
        tasks.append(libkirk.create_task(stop()))
        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=30)
            for data in results[:-1]:
                assert data["returncode"] != 0
                assert data["stdout"] == "ready\n"
            assert not await com.active()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def test_fetch_file_bad_args(self, com):
        """
        Test fetch_file method with bad arguments.
        """
        await com.communicate(iobuffer=Printer())

        with pytest.raises(ValueError):
            # pyrefly: ignore[bad-argument-type]
            await com.fetch_file(None)

        with pytest.raises(CommunicationError):
            await com.fetch_file("this_file_doesnt_exist")

    @pytest.fixture
    async def target_tmpdir(self, com):
        """
        Create and remove a private directory on the target.
        """
        await com.communicate(iobuffer=Printer())
        result = await com.run_command("mktemp -d /tmp/kirk-test.XXXXXXXX")
        assert result["returncode"] == 0
        path = result["stdout"].strip()
        assert path.startswith("/tmp/kirk-test.")
        try:
            yield path
        finally:
            if not await com.active():
                await asyncio.wait_for(com.communicate(), timeout=30)
            result = await asyncio.wait_for(
                com.run_command(f"rm -rf -- {shlex.quote(path)}"), timeout=30
            )
            assert result["returncode"] == 0

    async def test_fetch_file(self, com, target_tmpdir):
        """
        Test fetch_file method.
        """
        for i in range(0, 5):
            myfile = f"{target_tmpdir}/myfile{i}"
            result = await com.run_command(f"echo -n 'mytests' > {shlex.quote(myfile)}")
            assert result["returncode"] == 0
            data = await com.fetch_file(myfile)

            assert data == b"mytests"

    async def test_fetch_file_stop(self, com, target_tmpdir):
        """
        Test stop method when running fetch_file.
        """
        target = f"{target_tmpdir}/target_file"
        result = await com.run_command(f"mkfifo {shlex.quote(target)}")
        assert result["returncode"] == 0
        output = CommandOutput()
        # Opening the writer proves that fetch_file() has opened the FIFO reader.
        writer = libkirk.create_task(com.run_command(
            f"exec 3>{shlex.quote(target)}; printf data >&3; echo ready; exec sleep 60",
            iobuffer=output,
        ))
        task = libkirk.create_task(com.fetch_file(target))

        async def stop():
            await output.started.wait()
            assert not task.done()
            await com.stop(iobuffer=Printer())

        tasks = [task, writer, libkirk.create_task(stop())]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=30
            )
            assert isinstance(results[0], (bytes, CommunicationError))
            assert isinstance(results[1], dict), results[1]
            assert results[1]["returncode"] != 0
            assert results[2] is None
            assert not await com.active()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=5
            )

    async def test_cwd(self, com):
        """
        Test CWD constructor argument.
        """
        await com.communicate(iobuffer=Printer())

        ret = await com.run_command("echo -n $PWD", cwd="/tmp", iobuffer=Printer())

        assert ret["returncode"] == 0
        assert ret["stdout"].strip() == "/tmp"

    async def test_env(self, com):
        """
        Test ENV constructor argument.
        """
        await com.communicate(iobuffer=Printer())

        ret = await com.run_command(
            "echo -n $HELLO", env=dict(HELLO="ciao"), iobuffer=Printer()
        )

        assert ret["returncode"] == 0
        assert ret["stdout"].strip() == "ciao"


def test_discover(tmpdir):
    """
    Test if ComChannel implementations are correctly discovered.
    """
    impl = []
    impl.append(tmpdir / "chanA.py")
    impl.append(tmpdir / "chanB.py")
    impl.append(tmpdir / "chanC.txt")

    for index in range(0, len(impl)):
        impl[index].write(
            "from libkirk.com import ComChannel\n\n"
            f"class ComChannel{index}(ComChannel):\n"
            f"  _name = 'channel{index}'\n"
        )

    libkirk.com.discover(str(tmpdir), extend=False)

    channels = libkirk.com.get_channels()
    assert len(channels) == 2

    names = [c.name for c in channels]
    assert "channel0" in names
    assert "channel1" in names


def test_clone_channel(tmpdir):
    """
    Verify that channel can be cloned.
    """
    chanf = tmpdir / "chan.py"
    chanf.write(
        "from libkirk.com import ComChannel\n\n"
        "class MyChannel(ComChannel):\n"
        "  _name = 'mychan'\n"
    )

    libkirk.com.discover(str(tmpdir), extend=False)
    assert libkirk.com.clone_channel("mychan", "newchan")

    com = next((c for c in libkirk.com.get_channels() if c.name == "newchan"), None)
    assert com


def test_clone_channel_error(tmpdir):
    """
    Verify that unkown channel can't be cloned.
    """
    with pytest.raises(PluginError):
        libkirk.com.clone_channel("mychan", "newchan")
