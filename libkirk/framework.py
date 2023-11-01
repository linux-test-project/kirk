"""
.. module:: framework
    :platform: Linux
    :synopsis: framework definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.plugin import Plugin
from libkirk.results import TestResults


class FrameworkError(KirkException):
    """
    A generic framework exception.
    """


class Framework(Plugin):
    """
    Framework definition. Implement this class if you need to support more
    testing frameworks inside the application.
    """

    async def get_suites(self, sut: SUT) -> list:
        """
        Return the list of available suites inside SUT.
        :param sut: SUT object to communicate with
        :type sut: SUT
        :returns: list
        """
        raise NotImplementedError()

    async def find_command(self, sut: SUT, command: str) -> Test:
        """
        Search for command inside Framework folder and, if it's not found,
        search for command in the operating system. Then return a Test object
        which can be used to execute command.
        :param sut: SUT object to communicate with
        :type sut: SUT
        :param command: command to execute
        :type command: str
        :returns: Test
        """
        raise NotImplementedError()

    async def find_suite(self, sut: SUT, name: str) -> Suite:
        """
        Search for suite with given name inside SUT.
        :param sut: SUT object to communicate with
        :type sut: SUT
        :param suite: name of the suite
        :type suite: str
        :returns: Suite
        """
        raise NotImplementedError()

    async def read_result(
            self,
            test: Test,
            stdout: str,
            retcode: int,
            exec_t: float) -> TestResults:
        """
        Return test results accoding with runner output and Test definition.
        :param test: Test definition object
        :type test: Test
        :param stdout: test stdout
        :type stdout: str
        :param retcode: test return code
        :type retcode: int
        :param exec_t: test execution time in seconds
        :type exec_t: float
        :returns: TestResults
        """
        raise NotImplementedError()
