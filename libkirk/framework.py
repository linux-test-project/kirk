"""
.. module:: framework
    :platform: Linux
    :synopsis: framework definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import List

from libkirk.com import ComChannel
from libkirk.data import Suite, Test
from libkirk.plugin import Plugin
from libkirk.results import TestResults


class Framework(Plugin):
    """
    Framework definition. Implement this class if you need to support more
    testing frameworks inside the application.
    """

    async def get_suites(self, channel: ComChannel) -> List[str]:
        """
        Return the list of available suites.
        :param channel: communication channel
        :type channel: ComChannel
        :returns: list
        """
        raise NotImplementedError()

    async def find_command(self, channel: ComChannel, command: str) -> Test:
        """
        Search for command inside Framework folder and, if it's not found,
        search for command in the SUT. Then return a Test object which can be
        used to execute command.
        :param channel: communication channel
        :type channel: ComChannel
        :param command: command to execute
        :type command: str
        :returns: Test
        """
        raise NotImplementedError()

    async def find_suite(self, channel: ComChannel, name: str) -> Suite:
        """
        Search for suite with given name inside the SUT.
        :param channel: communication channel
        :type channel: ComChannel
        :param suite: name of the suite
        :type suite: str
        :returns: Suite
        """
        raise NotImplementedError()

    async def read_result(
        self, test: Test, stdout: str, retcode: int, exec_t: float
    ) -> TestResults:
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
