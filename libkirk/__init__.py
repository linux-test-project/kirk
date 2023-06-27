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


def cancel_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """
    Cancel all asyncio running tasks.
    """
    to_cancel = None

    # pylint: disable=no-member
    if sys.version_info >= (3, 7):
        to_cancel = asyncio.all_tasks(loop=loop)
    else:
        to_cancel = asyncio.Task.all_tasks(loop=loop)

    if not to_cancel:
        return

    for task in to_cancel:
        if task.cancelled():
            continue

        task.cancel()

    # pylint: disable=deprecated-argument
    if sys.version_info >= (3, 10):
        loop.run_until_complete(
            asyncio.gather(*to_cancel, return_exceptions=True))
    else:
        loop.run_until_complete(
            asyncio.gather(*to_cancel, loop=loop, return_exceptions=True))

    for task in to_cancel:
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


def run(coro: typing.Coroutine) -> typing.Any:
    """
    Run coroutine inside running event loop and it cancel all loop
    tasks at the end. Useful when we want to run the main() function.
    """
    loop = get_event_loop()

    def handler() -> None:
        cancel_tasks(loop)

        # we don't have to handle signal again
        loop.remove_signal_handler(signal.SIGTERM)
        loop.add_signal_handler(signal.SIGINT, lambda: None)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handler)

    try:
        return loop.run_until_complete(coro)
    finally:
        cancel_tasks(loop)


__all__ = [
    "KirkException",
    "events",
    "get_event_loop",
]
