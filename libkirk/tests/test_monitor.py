"""
Unittest for monitor module.
"""
import json
import asyncio
import pytest
import libkirk
from libkirk.io import AsyncFile
from libkirk.monitor import JSONFileMonitor

pytestmark = pytest.mark.asyncio

MONITOR_FILE = "monitor.json"


@pytest.fixture(autouse=True)
async def monitor(tmpdir):
    """
    Fixture containing json file monitor.
    """
    fpath = tmpdir / MONITOR_FILE

    # fill the file with garbage data before writing
    with open(fpath, 'w', encoding="utf-8") as data:
        data.write("garbage")

    obj = JSONFileMonitor(fpath)
    await obj.start()
    yield
    await obj.stop()


@pytest.fixture(autouse=True)
async def run_events():
    """
    Run kirk events at the beginning of the test
    and stop it at the end of the test.
    """
    async def start():
        await libkirk.events.start()

    libkirk.create_task(start())
    yield
    await libkirk.events.stop()


@pytest.fixture
async def read_monitor(tmpdir):
    """
    Read a single line inside the monitor file.
    """
    fpath = tmpdir / MONITOR_FILE

    async def _read():
        async with AsyncFile(fpath, 'r') as fdata:
            data = None
            while not data:
                data = await fdata.readline()

            return data

    async def _wrap(position, msg):
        for _ in range(0, position - 1):
            await asyncio.wait_for(_read(), 1)

        data = await asyncio.wait_for(_read(), 1)
        assert data == msg

    return _wrap


async def test_single_write(read_monitor):
    """
    Test if a single event will cause to write inside the monitor file
    only once.
    """
    msg = json.dumps({
        'type': "session_stopped",
        'message': {}
    })

    for _ in range(1, 10):
        await libkirk.events.fire("session_stopped")
        await read_monitor(1, msg)


async def test_override_events(tmpdir, read_monitor):
    """
    Test if we are correctly writing data inside monitor file.
    """
    await libkirk.events.fire("session_started", str(tmpdir))
    await libkirk.events.fire("kernel_panic")
    await libkirk.events.fire("session_stopped")

    msg = json.dumps({
        'type': "session_stopped",
        'message': {}
    })

    await read_monitor(3, msg)
