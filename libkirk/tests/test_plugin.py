"""
Unittests for framework module.
"""
import libkirk
import libkirk.plugin
from libkirk.sut import SUT


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
            "from libkirk.sut import SUT\n\n"
            f"class SUT{index}(SUT):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'mysut{index}'\n"
        )

    suts = libkirk.plugin.discover(SUT, str(tmpdir))

    assert len(suts) == 2
