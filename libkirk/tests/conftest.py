"""
Generic stuff for pytest.
"""

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


@pytest.fixture
def ltpdir(tmpdir):
    """
    Setup the temporary folder with LTP tests.
    """
    os.environ["LTPROOT"] = str(tmpdir)

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
