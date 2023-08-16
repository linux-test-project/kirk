"""
.. module:: __init__
    :platform: Linux
    :synopsis: application package definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import sys
import signal
import typing
import asyncio
from libkirk.events import EventsHandler


# Kirk version
VERSION = '1.1'


class KirkException(Exception):
    """
    The most generic exception that is raised by any module when
    something bad happens.
    """
    pass


events = EventsHandler()


def get_event_loop() -> asyncio.BaseEventLoop:
    """
    Return the current asyncio event loop.
    """
    loop = None

    try:
        loop = asyncio.get_running_loop()
    except (AttributeError, RuntimeError):
        pass

    if not loop:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            pass

    if not loop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop


def create_task(coro: typing.Coroutine) -> asyncio.Task:
    """
    Create a new task.
    """
    loop = get_event_loop()
    task = loop.create_task(coro)

    return task


def all_tasks(loop: asyncio.AbstractEventLoop) -> list:
    """
    Return the list of all running tasks for the specific loop.
    """
    tasks = None

    # pylint: disable=no-member
    if sys.version_info >= (3, 7):
        tasks = asyncio.all_tasks(loop=loop)
    else:
        tasks = asyncio.Task.all_tasks(loop=loop)

    return tasks


def cancel_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """
    Cancel all asyncio running tasks.
    """
    tasks = all_tasks(loop)
    if not tasks:
        return

    for task in tasks:
        if task.cancelled() or task.done():
            continue

        task.cancel()

    # pylint: disable=deprecated-argument
    if sys.version_info >= (3, 10):
        loop.run_until_complete(
            asyncio.gather(*tasks, return_exceptions=True))
    else:
        loop.run_until_complete(
            asyncio.gather(*tasks, loop=loop, return_exceptions=True))

    for task in tasks:
        if task.cancelled():
            continue

        if task.exception() is not None:
            loop.call_exception_handler({
                'message': 'unhandled exception during asyncio.run() shutdown',
                'exception': task.exception(),
                'task': task,
            })


def to_thread(callback: callable, *args: typing.Any) -> typing.Any:
    """
    Run callback inside a thread. This is useful for blocking I/O operations.
    """
    loop = get_event_loop()
    return loop.run_in_executor(None, callback, *args)


__all__ = [
    "KirkException",
    "events",
    "get_event_loop",
]
