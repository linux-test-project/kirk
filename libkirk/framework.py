"""
.. module:: framework
    :platform: Linux
    :synopsis: framework definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
from libkirk.sut import SUT
from libkirk.data import Suite


class Framework:
    """
    Framework definition. Implement this class if you need to support more
    testing frameworks inside the application.
    """

    @property
    def name(self) -> str:
        """
        Name of the framework.
        """
        raise NotImplementedError()

    def setup(self, **kwargs: dict) -> None:
        """
        Setup the framework.
        :param kwargs: framework configuration
        :type kwargs: dict
        """
        raise NotImplementedError()

    async def get_suites(self, sut: SUT) -> list:
        """
        Return the list of available suites inside SUT.
        :param sut: SUT object to communicate with
        :type sut: SUT
        :returns: list
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
