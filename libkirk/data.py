"""
.. module:: data
    :platform: Linux
    :synopsis: module containing input data handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import logging
from typing import Dict, List, Optional

LOGGER = logging.getLogger("kirk.data")


class Test:
    """
    Test definition class.
    """

    def __init__(
        self,
        name: str,
        cmd: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        args: Optional[List[str]] = None,
        parallelizable: bool = False,
    ) -> None:
        """
        :param name: name of the test
        :type name: str
        :param cmd: command to execute
        :type cmd: str
        :param cwd: current working directory of the command
        :type cwd: str
        :param env: environment variables used to run the command
        :type env: dict
        :param args: list of arguments
        :type args: list(str)
        :param parallelizable: if True, test can be run in parallel
        :type parallelizable: bool
        """
        if not name:
            raise ValueError("Test must have a name")

        if not cmd:
            raise ValueError("Test must have a command")

        self._name = name
        self._cmd = cmd
        self._cwd = cwd
        self._args = args if args else []
        self._env = env if env else {}
        self._parallelizable = parallelizable

    def __repr__(self) -> str:
        return (
            f"name: '{self._name}', "
            f"commmand: '{self._cmd}', "
            f"arguments: {self._args}, "
            f"cwd: '{self._cwd}', "
            f"environ: '{self._env}', "
            f"parallelizable: {self._parallelizable}"
        )

    @property
    def name(self) -> str:
        """
        Name of the test.
        """
        return self._name

    @property
    def command(self) -> str:
        """
        Command to execute test.
        """
        return self._cmd

    @property
    def arguments(self) -> List[str]:
        """
        Arguments of the command.
        """
        return self._args

    @property
    def parallelizable(self) -> bool:
        """
        If True, test can be run in parallel.
        """
        return self._parallelizable

    @property
    def cwd(self) -> Optional[str]:
        """
        Current working directory.
        """
        return self._cwd

    @property
    def env(self) -> Dict[str, str]:
        """
        Environment variables
        """
        return self._env

    @property
    def full_command(self) -> str:
        """
        Return the full command, with arguments as well.
        For example, if `command="ls"` and `arguments="-l -a"`,
        `full_command="ls -l -a"`.
        """
        cmd = self.command if self.command else ""
        if len(self.arguments) > 0:
            cmd += " "
            cmd += " ".join(self.arguments)

        return cmd

    def force_parallel(self) -> None:
        """
        Force test to be parallelizable.
        """
        self._parallelizable = True


class Suite:
    """
    Testing suite definition class.
    """

    def __init__(self, name: str, tests: List[Test]) -> None:
        """
        :param name: name of the testing suite
        :type name: str
        :param tests: tests of the suite
        :type tests: list
        """
        self._name = name
        self._tests = tests

    def __repr__(self) -> str:
        return f"name: '{self._name}', tests: {self._tests}"

    @property
    def name(self) -> str:
        """
        Name of the testing suite.
        """
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """
        Set the suite name.
        """
        if not value:
            raise ValueError("empty suite name")

        self._name = value

    @property
    def tests(self) -> List[Test]:
        """
        Tests definitions.
        """
        return self._tests
