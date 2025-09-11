"""
Unittests for framework module.
"""

import libkirk
import libkirk.plugin
from libkirk.framework import Framework
from libkirk.com import SUT, COM


def test_com(tmpdir):
    """
    Test if COM implementations are correctly loaded.
    """
    suts = []
    suts.append(tmpdir / "sutA.py")
    suts.append(tmpdir / "sutB.py")
    suts.append(tmpdir / "sutC.txt")

    for index in range(0, len(suts)):
        suts[index].write(
            "from libkirk.com import COM\n\n"
            f"class SUT{index}(COM):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'mysut{index}'\n"
        )

    suts = libkirk.plugin.discover(COM, str(tmpdir))

    assert len(suts) == 2


def test_sut(tmpdir):
    """
    Test if SUT implementations are correctly loaded.
    """
    suts = []
    suts.append(tmpdir / "sutA.py")
    suts.append(tmpdir / "sutB.py")
    suts.append(tmpdir / "sutC.txt")

    for index in range(0, len(suts)):
        suts[index].write(
            "from libkirk.com import SUT\n\n"
            f"class SUT{index}(SUT):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'mysut{index}'\n"
        )

    suts = libkirk.plugin.discover(SUT, str(tmpdir))

    assert len(suts) == 2


def test_framework(tmpdir):
    """
    Test if Framework implementations are correctly loaded.
    """
    suts = []
    suts.append(tmpdir / "frameworkA.py")
    suts.append(tmpdir / "frameworkB.py")
    suts.append(tmpdir / "frameworkC.txt")

    for index in range(0, len(suts)):
        suts[index].write(
            "from libkirk.framework import Framework\n\n"
            f"class Framework{index}(Framework):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'fw{index}'\n"
        )

    suts = libkirk.plugin.discover(Framework, str(tmpdir))

    assert len(suts) == 2
