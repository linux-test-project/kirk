"""
Unittests for framework module.
"""

import pytest
import libkirk
import libkirk.plugin
from libkirk.plugin import Plugin
from libkirk.framework import Framework


@pytest.fixture(autouse=True)
def setup(tmpdir):
    """
    Setup the temporary folder before tests.
    """
    plugins = []
    plugins.append(tmpdir / "pluginA.py")
    plugins.append(tmpdir / "pluginB.py")
    plugins.append(tmpdir / "pluginC.txt")

    for index in range(0, len(plugins)):
        plugins[index].write(
            "from libkirk.plugin import Plugin\n\n"
            "class MyPlugin(Plugin):\n"
            "    _name = 'myplug'\n"
        )


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


def test_clone(tmpdir):
    """
    Test if ``clone`` method properly forks inside ``Plugin``.
    """
    plugins = libkirk.plugin.discover(Plugin, str(tmpdir))
    newplugin = plugins[0].clone("myclone")

    assert newplugin.name == "myclone"
