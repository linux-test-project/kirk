"""
Unittests for com module.
"""

import pytest
import libkirk.com


@pytest.fixture(autouse=True)
def setup(tmpdir):
    """
    Setup the folder.
    """
    coms = []
    coms.append(tmpdir / "comA.py")
    coms.append(tmpdir / "comB.py")
    coms.append(tmpdir / "comC.txt")

    for index in range(0, len(coms)):
        coms[index].write(
            "from libkirk.com import COM\n\n"
            f"class MyCOM{index}(COM):\n"
            f"      _name = 'mycom{index}'\n"
        )

    suts = []
    suts.append(tmpdir / "sutA.py")
    suts.append(tmpdir / "sutB.py")
    suts.append(tmpdir / "sutC.txt")

    for index in range(0, len(suts)):
        suts[index].write(
            "from libkirk.com import SUT\n\n"
            f"class SUT{index}(SUT):\n"
            f"      _name = 'mysut{index}'\n"
        )


def test_discover(tmpdir):
    """
    Verify that discover will find SUT and COM plugins.
    """
    libkirk.com.discover(str(tmpdir))

    assert len(libkirk.com.get_loaded_com()) == 2
    assert len(libkirk.com.get_loaded_sut()) == 2


def test_discover_append(tmpdir):
    """
    Verify that discover will add more SUT and COM plugins if False is passed
    to discovery method.
    """
    libkirk.com.discover(str(tmpdir))

    assert len(libkirk.com.get_loaded_com()) == 2
    assert len(libkirk.com.get_loaded_sut()) == 2

    libkirk.com.discover(str(tmpdir), reset=False)

    assert len(libkirk.com.get_loaded_com()) == 4
    assert len(libkirk.com.get_loaded_sut()) == 4


def test_discover_reset(tmpdir):
    """
    Verify that discover will delete all SUT and COM plugins if True is passed
    to discovery method.
    """
    libkirk.com.discover(str(tmpdir))

    assert len(libkirk.com.get_loaded_com()) == 2
    assert len(libkirk.com.get_loaded_sut()) == 2

    libkirk.com.discover(str(tmpdir), reset=True)

    assert len(libkirk.com.get_loaded_com()) == 2
    assert len(libkirk.com.get_loaded_sut()) == 2


def test_get_com(tmpdir):
    """
    Verify that we can get the requested COM plugin.
    """
    libkirk.com.discover(str(tmpdir))

    assert libkirk.com.get_com("mycom0")


def test_clone_com(tmpdir):
    """
    Verify that COM object can be cloned.
    """
    libkirk.com.discover(str(tmpdir))
    assert libkirk.com.clone_com("mycom0", "newcom0")

    names = [com.name for com in libkirk.com.get_loaded_com()]
    assert "newcom0" in names
