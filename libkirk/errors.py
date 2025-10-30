"""
.. module:: errors
    :platform: Linux
    :synopsis: module containing errors raised by kirk.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""


class KirkException(Exception):
    """
    The most generic exception that is raised by any module. All kirk errors
    derives from this class.
    """


class PluginError(KirkException):
    """
    Raised when plugins operations have failed.
    """


class CommunicationError(KirkException):
    """
    Raised when error occurs during channels communication.
    """


class SUTError(KirkException):
    """
    Raised when error occurs in SUT.
    """


class KernelPanicError(KirkException):
    """
    Raised during kernel panic.
    """


class KernelTaintedError(KirkException):
    """
    Raised when kernel is tainted.
    """


class KernelTimeoutError(KirkException):
    """
    Raised when kernel is not responding anymore.
    """


class FrameworkError(KirkException):
    """
    Raised when an error occurs inside a framework.
    """


class ExporterError(KirkException):
    """
    Raised when an error occurs during Exporter operations.
    """


class LTXError(KirkException):
    """
    Raised when an error occurs during LTX execution.
    """


class SchedulerError(KirkException):
    """
    Raised when an error occurs during Scheduler operations.
    """


class SessionError(KirkException):
    """
    Raised when an error occurs during Session operations.
    """
