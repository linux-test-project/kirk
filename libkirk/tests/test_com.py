"""
Test ComChannel implementations.
"""

import asyncio
import logging
import os
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


@pytest.fixture
def com():
    """
    Expose the ComChannel implementation via this fixture in order to test it.
    """
    raise NotImplementedError()


@pytest.mark.asyncio
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

    @pytest.fixture
    def com_stop_setup(self, request):
        """
        Setup sleep time before calling stop after communicate.
        By changing multiply factor it's possible to tweak stop sleep and
        change the behaviour of `test_stop_communicate`.
        """
        return request.param * 1.0

    @pytest.mark.parametrize("com_stop_setup", [1, 2], indirect=True)
    async def test_communicate_stop(self, com, com_stop_setup):
        """
        Test stop method when running communicate.
        """

        async def stop():
            await asyncio.sleep(com_stop_setup)
            await com.stop(iobuffer=Printer())

        await asyncio.gather(
            *[com.communicate(iobuffer=Printer()), stop()], return_exceptions=True
        )

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

        async def stop():
            await asyncio.sleep(0.2)
            await com.stop(iobuffer=Printer())

        async def test():
            res = await com.run_command("sleep 2")

            assert res["returncode"] != 0
            assert 0 < res["exec_time"] < 2

        await asyncio.gather(*[test(), stop()])

    async def test_run_command_parallel(self, com):
        """
        Execute run_command in parallel.
        """
        if not com.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await com.communicate(iobuffer=Printer())

        exec_count = os.cpu_count()
        coros = [com.run_command(f"echo {i}") for i in range(exec_count)]

        results = await asyncio.gather(*coros)

        for data in results:
            assert data["returncode"] == 0
            assert 0 <= int(data["stdout"]) < exec_count
            assert 0 < data["exec_time"] < time.time()

    async def test_run_command_stop_parallel(self, com):
        """
        Execute multiple run_command in parallel, then call stop().
        """
        if not com.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await com.communicate(iobuffer=Printer())

        async def stop():
            await asyncio.sleep(0.2)
            await com.stop(iobuffer=Printer())

        async def test():
            exec_count = os.cpu_count()
            coros = [com.run_command("sleep 2") for i in range(exec_count)]
            results = await asyncio.gather(*coros, return_exceptions=True)

            for data in results:
                if not isinstance(data, dict):
                    # we also have stop() return
                    continue

                assert data["returncode"] != 0
                assert 0 < data["exec_time"] < 2

        await asyncio.gather(*[test(), stop()])

    async def test_fetch_file_bad_args(self, com):
        """
        Test fetch_file method with bad arguments.
        """
        await com.communicate(iobuffer=Printer())

        with pytest.raises(ValueError):
            await com.fetch_file(None)

        with pytest.raises(CommunicationError):
            await com.fetch_file("this_file_doesnt_exist")

    async def test_fetch_file(self, com):
        """
        Test fetch_file method.
        """
        await com.communicate(iobuffer=Printer())

        for i in range(0, 5):
            myfile = f"/tmp/myfile{i}"
            await com.run_command(f"echo -n 'mytests' > {myfile}")
            data = await com.fetch_file(myfile)

            assert data == b"mytests"

    async def test_fetch_file_stop(self, com):
        """
        Test stop method when running fetch_file.
        """
        target = "/tmp/target_file"
        await com.communicate(iobuffer=Printer())

        async def fetch():
            (await com.run_command(f"truncate -s {1024 * 1024 * 1024} {target}"),)
            await com.fetch_file(target)

        async def stop():
            await asyncio.sleep(2)
            await com.stop(iobuffer=Printer())

        libkirk.create_task(fetch())

        await stop()

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
