"""
.. module:: __init__
    :platform: Linux
    :synopsis: application package definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import sys
import typing
from typing import Callable

from libkirk.evt import EventsHandler

# Kirk version
__version__ = "3.2.1"


events = EventsHandler()


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Return the current asyncio event loop.
    """
    try:
        return asyncio.get_running_loop()
    except (AttributeError, RuntimeError):
        pass

    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def create_task(coro: typing.Coroutine) -> asyncio.Task:
    """
    Create a new task.
    """
    return get_event_loop().create_task(coro)


def all_tasks(loop: asyncio.AbstractEventLoop) -> set:
    """
    Return the list of all running tasks for the specific loop.
    """
    # Maintain Python 3.6 compatibility
    if sys.version_info >= (3, 7):
        return asyncio.all_tasks(loop=loop)
    else:
        return asyncio.Task.all_tasks(loop=loop)


def cancel_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """
    Cancel all asyncio running tasks.
    """
    tasks = all_tasks(loop)
    if not tasks:
        return

    tasks_to_cancel = []
    for task in tasks:
        if not (task.cancelled() or task.done()):
            task.cancel()
            tasks_to_cancel.append(task)

    # Maintain Python 3.6 compatibility
    if sys.version_info >= (3, 10):
        # pyrefly: ignore[bad-argument-type]
        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    else:
        loop.run_until_complete(
            # pyrefly: ignore[bad-argument-type]
            asyncio.gather(*tasks, loop=loop, return_exceptions=True)
        )

    for task in tasks_to_cancel:
        if not task.cancelled() and task.exception() is not None:
            loop.call_exception_handler(
                {
                    "message": "unhandled exception during asyncio.run() shutdown",
                    "exception": task.exception(),
                    "task": task,
                }
            )


def to_thread(callback: Callable, *args: typing.Any) -> typing.Any:
    """
    Run callback inside a thread. This is useful for blocking I/O operations.
    """
    return get_event_loop().run_in_executor(None, callback, *args)


__all__ = [
    "events",
    "get_event_loop",
]
