"""
Generic stuff for pytest.
"""

import asyncio
import os

import pytest

import libkirk
import libkirk.com
import libkirk.sut


def pytest_sessionfinish(session, exitstatus):
    """
    Cleanup tasks when session finishes.
    """
    loop = libkirk.get_event_loop()
    libkirk.cancel_tasks(loop)
    loop.close()


@pytest.fixture(scope="session")
def event_loop():
    """
    Current event loop. Keep it in session scope, otherwise tests which
    will use same coroutines will be associated to different event_loop.
    In this way, pytest-asyncio plugin will work properly.
    """
    yield libkirk.get_event_loop()


@pytest.fixture(autouse=True, scope="function")
def _discover_plugins():
    """
    Discover plugins before running tests.
    """
    currdir = os.path.dirname(os.path.realpath(__file__))

    libkirk.com.discover(os.path.join(currdir, "..", "channels"), extend=False)
    libkirk.sut.discover(os.path.join(currdir, ".."), extend=False)


@pytest.fixture(autouse=True, scope="function")
def _reset_events():
    """
    Reset global events between tests to prevent event handler leakage.
    """
    yield
    libkirk.events.reset()


@pytest.fixture
async def run_events(_reset_events):
    """
    Run the event consumer and always stop and await it after the test.
    """
    task = libkirk.create_task(libkirk.events.start())
    await asyncio.sleep(0)
    try:
        yield
    finally:
        try:
            await asyncio.wait_for(libkirk.events.stop(), timeout=5)
        finally:
            if not task.done():
                task.cancel()
            results = await asyncio.wait_for(
                asyncio.gather(task, return_exceptions=True), timeout=5
            )
            assert results[0] is None or isinstance(results[0], asyncio.CancelledError)


@pytest.fixture
def ltpdir(tmpdir, monkeypatch):
    """
    Setup the temporary folder with LTP tests.
    """
    monkeypatch.setenv("LTPROOT", str(tmpdir))

    tmpdir.mkdir("testcases").mkdir("bin")
    runtest = tmpdir.mkdir("runtest")

    suite01 = runtest / "suite01"
    suite01.write_text(
        "test01 echo -n ciao\ntest02 echo -n ciao\n",
        encoding="utf-8")

    suite02 = runtest / "suite02"
    suite02.write_text(
        "test01 echo -n ciao\ntest02 sleep 0.2 && echo -n ciao",
        encoding="utf-8")

    sleep = runtest / "sleep"
    sleep.write_text(
        "sleep01 sleep 2\nsleep02 sleep 2",
        encoding="utf-8")

    environ = runtest / "environ"
    environ.write_text("test01 echo -n $hello",
        encoding="utf-8")

    kernel_panic = runtest / "kernel_panic"
    kernel_panic.write_text(
        "test01 echo 'Kernel panic'\ntest02 sleep 0.2",
        encoding="utf-8")

    return tmpdir
