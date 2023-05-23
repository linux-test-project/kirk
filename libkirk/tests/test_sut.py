"""
Test AsyncSUT implementations.
"""
import os
import time
import asyncio
import logging
import pytest
import libkirk
from libkirk.sut import IOBuffer
from libkirk.sut import SUTError


pytestmark = pytest.mark.asyncio


class Printer(IOBuffer):
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.host")

    async def write(self, data: str) -> None:
        print(data, end="")


@pytest.fixture
def sut():
    """
    Expose the SUT implementation via this fixture in order to test it.
    """
    raise NotImplementedError()


class _TestSUT:
    """
    Generic tests for SUT implementation.
    """

    _logger = logging.getLogger("test.asyncsut")

    def test_config_help(self, sut):
        """
        Test if config_help has the right type.
        """
        assert isinstance(sut.config_help, dict)

    async def test_ping_no_running(self, sut):
        """
        Test ping method with no running sut.
        """
        with pytest.raises(SUTError):
            await sut.ping()

    async def test_ping(self, sut):
        """
        Test ping method.
        """
        await sut.communicate(iobuffer=Printer())
        ping_t = await sut.ping()
        assert ping_t > 0

    async def test_get_info(self, sut):
        """
        Test get_info method.
        """
        await sut.communicate(iobuffer=Printer())
        info = await sut.get_info()

        assert info["distro"]
        assert info["distro_ver"]
        assert info["kernel"]
        assert info["arch"]

    async def test_get_tainted_info(self, sut):
        """
        Test get_tainted_info.
        """
        await sut.communicate(iobuffer=Printer())
        code, messages = await sut.get_tainted_info()

        assert code >= 0
        assert isinstance(messages, list)

    async def test_communicate(self, sut):
        """
        Test communicate method.
        """
        await sut.communicate(iobuffer=Printer())
        with pytest.raises(SUTError):
            await sut.communicate(iobuffer=Printer())

    async def test_ensure_communicate(self, sut):
        """
        Test ensure_communicate method.
        """
        await sut.ensure_communicate(iobuffer=Printer())
        with pytest.raises(SUTError):
            await sut.ensure_communicate(iobuffer=Printer(), retries=1)

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Setup sleep time before calling stop after communicate.
        By changing multiply factor it's possible to tweak stop sleep and
        change the behaviour of `test_stop_communicate`.
        """
        return request.param * 1.0

    @pytest.mark.parametrize("sut_stop_sleep", [1, 2], indirect=True)
    async def test_communicate_stop(self, sut, sut_stop_sleep):
        """
        Test stop method when running communicate.
        """
        async def stop():
            await asyncio.sleep(sut_stop_sleep)
            await sut.stop(iobuffer=Printer())

        await asyncio.gather(*[
            sut.communicate(iobuffer=Printer()),
            stop()
        ], return_exceptions=True)

    async def test_run_command(self, sut):
        """
        Execute run_command once.
        """
        await sut.communicate(iobuffer=Printer())
        res = await sut.run_command("echo 0")

        assert res["returncode"] == 0
        assert int(res["stdout"]) == 0
        assert 0 < res["exec_time"] < time.time()

    async def test_run_command_stop(self, sut):
        """
        Execute run_command once, then call stop().
        """
        await sut.communicate(iobuffer=Printer())

        async def stop():
            await asyncio.sleep(0.2)
            await sut.stop(iobuffer=Printer())

        async def test():
            res = await sut.run_command("sleep 2")

            assert res["returncode"] != 0
            assert 0 < res["exec_time"] < 2

        await asyncio.gather(*[
            test(),
            stop()
        ])

    async def test_run_command_parallel(self, sut):
        """
        Execute run_command in parallel.
        """
        if not sut.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await sut.communicate(iobuffer=Printer())

        exec_count = os.cpu_count()
        coros = [sut.run_command(f"echo {i}")
                 for i in range(exec_count)]

        results = await asyncio.gather(*coros)

        for data in results:
            assert data["returncode"] == 0
            assert 0 <= int(data["stdout"]) < exec_count
            assert 0 < data["exec_time"] < time.time()

    async def test_run_command_stop_parallel(self, sut):
        """
        Execute multiple run_command in parallel, then call stop().
        """
        if not sut.parallel_execution:
            pytest.skip(reason="Parallel execution is not supported")

        await sut.communicate(iobuffer=Printer())

        async def stop():
            await asyncio.sleep(0.2)
            await sut.stop(iobuffer=Printer())

        async def test():
            exec_count = os.cpu_count()
            coros = [sut.run_command("sleep 2")
                     for i in range(exec_count)]
            results = await asyncio.gather(*coros, return_exceptions=True)

            for data in results:
                if not isinstance(data, dict):
                    # we also have stop() return
                    continue

                assert data["returncode"] != 0
                assert 0 < data["exec_time"] < 2

        await asyncio.gather(*[
            test(),
            stop()
        ])

    async def test_fetch_file_bad_args(self, sut):
        """
        Test fetch_file method with bad arguments.
        """
        await sut.communicate(iobuffer=Printer())

        with pytest.raises(ValueError):
            await sut.fetch_file(None)

        with pytest.raises(SUTError):
            await sut.fetch_file('this_file_doesnt_exist')

    async def test_fetch_file(self, sut):
        """
        Test fetch_file method.
        """
        await sut.communicate(iobuffer=Printer())

        for i in range(0, 5):
            myfile = f"/tmp/myfile{i}"
            await sut.run_command(f"echo -n 'mytests' > {myfile}")
            data = await sut.fetch_file(myfile)

            assert data == b"mytests"

    async def test_fetch_file_stop(self, sut):
        """
        Test stop method when running fetch_file.
        """
        target = "/tmp/target_file"
        await sut.communicate(iobuffer=Printer())

        async def fetch():
            await sut.run_command(f"truncate -s {1024*1024*1024} {target}"),
            await sut.fetch_file(target)

        async def stop():
            await asyncio.sleep(2)
            await sut.stop(iobuffer=Printer())

        libkirk.create_task(fetch())

        await stop()

    async def test_cwd(self, sut):
        """
        Test CWD constructor argument.
        """
        await sut.communicate(iobuffer=Printer())

        ret = await sut.run_command(
            "echo -n $PWD",
            cwd="/tmp",
            iobuffer=Printer())

        assert ret["returncode"] == 0
        assert ret["stdout"].strip() == "/tmp"

    async def test_env(self, sut):
        """
        Test ENV constructor argument.
        """
        await sut.communicate(iobuffer=Printer())

        ret = await sut.run_command(
            "echo -n $HELLO",
            env=dict(HELLO="ciao"),
            iobuffer=Printer())

        assert ret["returncode"] == 0
        assert ret["stdout"].strip() == "ciao"
