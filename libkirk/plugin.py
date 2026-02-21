"""
.. module:: plugin
    :platform: Linux
    :synopsis: generic plugin handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import importlib
import importlib.util
import inspect
import os
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    TypeVar,
)

_Self = TypeVar("_Self", bound="Plugin")


class Plugin:
    """
    Generic plugin definition.
    """

    _name = ""

    def setup(self, **kwargs: Dict[str, Any]) -> None:
        """
        Initialize plugin using configuration dictionary.

        :param kwargs: SUT configuration.
        :type kwargs: dict
        """
        raise NotImplementedError()

    @property
    def config_help(self) -> Dict[str, str]:
        """
        Associate each configuration option with a help message.
        This is used by the main menu application to generate --help message.

        :returns: Dictionary that associates options to help messages.
        :rtype: dict
        """
        raise NotImplementedError()

    @property
    def name(self) -> str:
        """
        :return: Unique name identifier of the plugin.
        :rtype: str
        """
        return self._name

    def clone(self, name: str) -> _Self:
        """
        Copy plugin and return a new instance with a given name.
        Make sure that name is unique, so external modules can
        recognize it.

        :param name: Unique identifier string given to the plugin.
        :type name: str
        :return: Cloned plugin.
        :rtype: Plugin
        """
        obj = self.__class__()
        obj._name = name

        # pyrefly:ignore[bad-return]
        return obj


def discover(mytype: type, folder: str) -> List[Plugin]:
    """
    Discover mytype implementations inside a specific folder.

    :param mtype: Type of the object we are searching for.
    :type mtype: type
    :param folder: Folder where to search for mtype.
    :type folder: str
    :return: List of discovered plugins.
    :rtype: list(Plugin)
    """
    if not folder or not os.path.isdir(folder):
        raise ValueError("Discover folder doesn't exist")

    loaded_obj = []

    # use pathlib for more efficient iteration
    folder_path = Path(folder)

    for py_file in folder_path.glob("*.py"):
        if not py_file.is_file():
            continue

        spec = importlib.util.spec_from_file_location("obj", str(py_file))
        if not spec or not spec.loader:
            continue

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        module_name = module.__name__

        members = inspect.getmembers(module, inspect.isclass)
        for _, klass in members:
            if (
                klass.__module__ != module_name
                or klass is mytype
                or klass in loaded_obj
            ):
                continue

            if issubclass(klass, mytype):
                loaded_obj.append(klass())

    if loaded_obj:
        loaded_obj.sort(key=lambda x: x.name)

    return loaded_obj
