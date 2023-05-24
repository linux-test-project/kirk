"""
.. module:: plugin
    :platform: Linux
    :synopsis: generic plugin handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import inspect
import importlib
import importlib.util


class Plugin:
    """
    Generic plugin definition.
    """

    def setup(self, **kwargs: dict) -> None:
        """
        Initialize plugin using configuration dictionary.
        :param kwargs: SUT configuration
        :type kwargs: dict
        """
        raise NotImplementedError()

    @property
    def config_help(self) -> dict:
        """
        Associate each configuration option with a help message.
        This is used by the main menu application to generate --help message.
        :returns: dict
        """
        raise NotImplementedError()

    @property
    def name(self) -> str:
        """
        Name of the plugin.
        """
        raise NotImplementedError()


def discover(mytype: type, folder: str) -> list:
    """
    Discover ``mytype`` implementations inside a specific folder.
    """
    if not folder or not os.path.isdir(folder):
        raise ValueError("Discover folder doesn't exist")

    loaded_obj = []

    for myfile in os.listdir(folder):
        if not myfile.endswith('.py'):
            continue

        path = os.path.join(folder, myfile)
        if not os.path.isfile(path):
            continue

        spec = importlib.util.spec_from_file_location('obj', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        members = inspect.getmembers(module, inspect.isclass)
        for _, klass in members:
            if klass.__module__ != module.__name__ or \
                    klass is mytype or \
                    klass in loaded_obj:
                continue

            if issubclass(klass, mytype):
                loaded_obj.append(klass())

    if len(loaded_obj) > 0:
        loaded_obj.sort(key=lambda x: x.name)

    return loaded_obj
