"""
.. module:: data
    :platform: Linux
    :synopsis: module containing input data handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import logging

LOGGER = logging.getLogger("kirk.data")


class Suite:
    """
    Testing suite definition class.
    """

    def __init__(self, name: str, tests: list) -> None:
        """
        :param name: name of the testing suite
        :type name: str
        :param tests: tests of the suite
        :type tests: list
        """
        self._name = name
        self._tests = tests

    def __repr__(self) -> str:
        return \
            f"name: '{self._name}', " \
            f"tests: {self._tests}"

    @property
    def name(self):
        """
        Name of the testing suite.
        """
        return self._name

    @property
    def tests(self):
        """
        Tests definitions.
        """
        return self._tests


class Test:
    """
    Test definition class.
    """

    def __init__(self, **kwargs: dict) -> None:
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
        self._name = kwargs.get("name", None)
        self._cmd = kwargs.get("cmd", None)
        self._args = kwargs.get("args", [])
        self._cwd = kwargs.get("cwd", None)
        self._env = kwargs.get("env", {})
        self._parallelizable = kwargs.get("parallelizable", False)

    def __repr__(self) -> str:
        return \
            f"name: '{self._name}', " \
            f"commmand: '{self._cmd}', " \
            f"arguments: {self._args}, " \
            f"cwd: '{self._cwd}', " \
            f"environ: '{self._env}', " \
            f"parallelizable: {self._parallelizable}"

    @property
    def name(self):
        """
        Name of the test.
        """
        return self._name

    @property
    def command(self):
        """
        Command to execute test.
        """
        return self._cmd

    @property
    def arguments(self):
        """
        Arguments of the command.
        """
        return self._args

    @property
    def parallelizable(self):
        """
        If True, test can be run in parallel.
        """
        return self._parallelizable

    @property
    def cwd(self):
        """
        Current working directory.
        """
        return self._cwd

    @property
    def env(self):
        """
        Environment variables
        """
        return self._env

    @property
    def full_command(self):
        """
        Return the full command, with arguments as well.
        For example, if `command="ls"` and `arguments="-l -a"`,
        `full_command="ls -l -a"`.
        """
        cmd = self.command
        if len(self.arguments) > 0:
            cmd += ' '
            cmd += ' '.join(self.arguments)

        return cmd
