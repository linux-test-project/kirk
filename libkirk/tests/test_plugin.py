"""
Unittests for plugin module.
"""

import pytest
import libkirk
import libkirk.plugin
from libkirk.plugin import Plugin


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


def test_discover(tmpdir):
    """
    Test if libkirk.plugin.discover() is currently working on multiple
    plugins definitions being python modules.
    """
    plugins = libkirk.plugin.discover(Plugin, str(tmpdir))
    assert len(plugins) == 2


def test_clone(tmpdir):
    """
    Test if ``clone`` method properly forks inside ``Plugin``.
    """
    plugins = libkirk.plugin.discover(Plugin, str(tmpdir))
    newplugin = plugins[0].clone("myclone")

    assert newplugin.name == "myclone"
