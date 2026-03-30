"""
Unittest for monitor module.
"""

import asyncio
import json

import pytest

import libkirk
from libkirk.io import AsyncFile
from libkirk.monitor import JSONFileMonitor

MONITOR_FILE = "monitor.json"


@pytest.fixture(autouse=True)
async def monitor(tmpdir):
    """
    Fixture containing json file monitor.
    """
    fpath = tmpdir / MONITOR_FILE

    # fill the file with garbage data before writing
    with open(fpath, "w", encoding="utf-8") as data:
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
        data = None
        while not data:
            async with AsyncFile(fpath, "r") as fdata:
                data = await fdata.readline()

            if data:
                try:
                    json.loads(data)
                except json.JSONDecodeError:
                    data = None
                    await asyncio.sleep(0.01)

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
    msg = json.dumps({"type": "session_stopped", "message": {}})

    for _ in range(1, 10):
        await libkirk.events.fire("session_stopped")
        await read_monitor(1, msg)


async def test_override_events(tmpdir, read_monitor):
    """
    Test if we are correctly writing data inside monitor file.
    """
    await libkirk.events.fire("session_started", [], str(tmpdir))
    await libkirk.events.fire("kernel_panic")
    await libkirk.events.fire("session_stopped")

    msg = json.dumps({"type": "session_stopped", "message": {}})

    await read_monitor(3, msg)


async def test_session_restore(read_monitor):
    """
    Test session_restore event.
    """
    await libkirk.events.fire("session_restore", "/tmp/restore")
    msg = json.dumps({"type": "session_restore", "message": {"restore": "/tmp/restore"}})
    await read_monitor(1, msg)


async def test_sut_stdout(read_monitor):
    """
    Test sut_stdout event.
    """
    await libkirk.events.fire("sut_stdout", "mysut", "hello")
    msg = json.dumps({"type": "sut_stdout", "message": {"sut": "mysut", "data": "hello"}})
    await read_monitor(1, msg)


async def test_sut_start(read_monitor):
    """
    Test sut_start event.
    """
    await libkirk.events.fire("sut_start", "mysut")
    msg = json.dumps({"type": "sut_start", "message": {"sut": "mysut"}})
    await read_monitor(1, msg)


async def test_sut_stop(read_monitor):
    """
    Test sut_stop event.
    """
    await libkirk.events.fire("sut_stop", "mysut")
    msg = json.dumps({"type": "sut_stop", "message": {"sut": "mysut"}})
    await read_monitor(1, msg)


async def test_sut_restart(read_monitor):
    """
    Test sut_restart event.
    """
    await libkirk.events.fire("sut_restart", "mysut")
    msg = json.dumps({"type": "sut_restart", "message": {"sut": "mysut"}})
    await read_monitor(1, msg)


async def test_sut_not_responding(read_monitor):
    """
    Test sut_not_responding event.
    """
    await libkirk.events.fire("sut_not_responding")
    msg = json.dumps({"type": "sut_not_responding", "message": {}})
    await read_monitor(1, msg)


async def test_run_cmd_start(read_monitor):
    """
    Test run_cmd_start event.
    """
    await libkirk.events.fire("run_cmd_start", "ls -la")
    msg = json.dumps({"type": "run_cmd_start", "message": {"cmd": "ls -la"}})
    await read_monitor(1, msg)


async def test_run_cmd_stop(read_monitor):
    """
    Test run_cmd_stop event.
    """
    await libkirk.events.fire("run_cmd_stop", "ls -la", "output", 0)
    msg = json.dumps({
        "type": "run_cmd_stop",
        "message": {"command": "ls -la", "stdout": "output", "returncode": 0},
    })
    await read_monitor(1, msg)


async def test_test_started(read_monitor):
    """
    Test test_started event.
    """
    from libkirk.data import Test

    test = Test(name="mytest", cmd="echo", args=["-n", "hello"])

    await libkirk.events.fire("test_started", test)
    msg = json.dumps({
        "type": "test_started",
        "message": {"test": {
            "name": "mytest",
            "command": "echo",
            "arguments": ["-n", "hello"],
            "parallelizable": False,
            "cwd": None,
            "env": {},
        }},
    })
    await read_monitor(1, msg)


async def test_test_stdout(read_monitor):
    """
    Test test_stdout event.
    """
    from libkirk.data import Test

    test = Test(name="mytest", cmd="echo", args=["-n", "hello"])

    await libkirk.events.fire("test_stdout", test, "output")
    msg = json.dumps({
        "type": "test_stdout",
        "message": {
            "test": {
                "name": "mytest",
                "command": "echo",
                "arguments": ["-n", "hello"],
                "parallelizable": False,
                "cwd": None,
                "env": {},
            },
            "data": "output",
        },
    })
    await read_monitor(1, msg)


async def test_test_timed_out(read_monitor):
    """
    Test test_timed_out event.
    """
    from libkirk.data import Test

    test = Test(name="mytest", cmd="echo", args=["-n", "hello"])

    await libkirk.events.fire("test_timed_out", test, 30)
    msg = json.dumps({
        "type": "test_timed_out",
        "message": {
            "test": {
                "name": "mytest",
                "command": "echo",
                "arguments": ["-n", "hello"],
                "parallelizable": False,
                "cwd": None,
                "env": {},
            },
            "timeout": 30,
        },
    })
    await read_monitor(1, msg)


async def test_suite_started(read_monitor):
    """
    Test suite_started event.
    """
    from libkirk.data import Test, Suite

    test = Test(name="t1", cmd="echo")
    suite = Suite("mysuite", [test])

    await libkirk.events.fire("suite_started", suite)
    msg = json.dumps({
        "type": "suite_started",
        "message": {
            "name": "mysuite",
            "tests": [{
                "name": "t1",
                "command": "echo",
                "arguments": [],
                "parallelizable": False,
                "cwd": None,
                "env": {},
            }],
        },
    })
    await read_monitor(1, msg)


async def test_suite_timeout(read_monitor):
    """
    Test suite_timeout event.
    """
    from libkirk.data import Test, Suite

    test = Test(name="t1", cmd="echo")
    suite = Suite("mysuite", [test])

    await libkirk.events.fire("suite_timeout", suite, 60.0)
    msg = json.dumps({
        "type": "suite_timeout",
        "message": {
            "suite": {
                "name": "mysuite",
                "tests": [{
                    "name": "t1",
                    "command": "echo",
                    "arguments": [],
                    "parallelizable": False,
                    "cwd": None,
                    "env": {},
                }],
            },
            "timeout": 60.0,
        },
    })
    await read_monitor(1, msg)


async def test_session_warning(read_monitor):
    """
    Test session_warning event.
    """
    await libkirk.events.fire("session_warning", "beware")
    msg = json.dumps({"type": "session_warning", "message": {"message": "beware"}})
    await read_monitor(1, msg)


async def test_session_error(read_monitor):
    """
    Test session_error event.
    """
    await libkirk.events.fire("session_error", "oops")
    msg = json.dumps({"type": "session_error", "message": {"error": "oops"}})
    await read_monitor(1, msg)


async def test_kernel_tainted(read_monitor):
    """
    Test kernel_tainted event.
    """
    await libkirk.events.fire("kernel_tainted", "proprietary module")
    msg = json.dumps({"type": "kernel_tainted", "message": {"message": "proprietary module"}})
    await read_monitor(1, msg)
