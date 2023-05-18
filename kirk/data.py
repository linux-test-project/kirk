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


PARALLEL_BLACKLIST = [
    "needs_root",
    "needs_device",
    "mount_device",
    "mntpoint",
    "resource_file",
    "format_device",
    "save_restore",
    "max_runtime"
]


# pylint: disable=too-many-locals
async def read_runtest(
        suite_name: str,
        content: str,
        metadata: dict = None) -> Suite:
    """
    It reads a runtest file content and it returns a Suite object.
    :param suite_name: name of the test suite
    :type suite_name: str
    :param content: content of the runtest file
    :type content: str
    :param metadata: metadata JSON file content
    :type metadata: dict
    :returns: Suite
    """
    if not content:
        raise ValueError("content is empty")

    LOGGER.info("collecting testing suite: %s", suite_name)

    metadata_tests = None
    if metadata:
        LOGGER.info("Reading metadata content")
        metadata_tests = metadata.get("tests", None)

    tests = []
    lines = content.split('\n')
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue

        LOGGER.debug("Test declaration: %s", line)

        parts = line.split()
        if len(parts) < 2:
            raise ValueError("Test declaration is not defining command")

        test_name = parts[0]
        test_cmd = parts[1]
        test_args = []

        if len(parts) >= 3:
            test_args = parts[2:]

        parallelizable = True

        if not metadata_tests:
            # no metadata no party
            parallelizable = False
        else:
            test_params = metadata_tests.get(test_name, None)
            if test_params:
                LOGGER.info("Found %s test params in metadata", test_name)
                LOGGER.debug("params=%s", test_params)

            if test_params is None:
                # this probably means test is not using new LTP API,
                # so we can't decide if test can run in parallel or not
                parallelizable = False
            else:
                for blacklist_param in PARALLEL_BLACKLIST:
                    if blacklist_param in test_params:
                        parallelizable = False
                        break

        if not parallelizable:
            LOGGER.info("Test '%s' is not parallelizable", test_name)
        else:
            LOGGER.info("Test '%s' is parallelizable", test_name)

        test = Test(
            test_name,
            test_cmd,
            test_args,
            parallelizable=parallelizable)

        tests.append(test)

        LOGGER.debug("test: %s", test)

    LOGGER.debug("Collected tests: %d", len(tests))

    suite = Suite(suite_name, tests)

    LOGGER.debug(suite)
    LOGGER.info("Collected testing suite: %s", suite_name)

    return suite
