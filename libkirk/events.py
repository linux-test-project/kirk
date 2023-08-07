"""
.. module:: events
    :platform: Linux
    :synopsis: events handler implementation module

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import typing
import logging
import asyncio


class EventsHandler:
    """
    This class implements event loop and events handling.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.events")
        self._tasks = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._events = {}
        self._stop = False

    def reset(self) -> None:
        """
        Reset the entire events queue.
        """
        self._logger.info("Reset events queue")
        self._events.clear()

    def is_registered(self, event_name: str) -> bool:
        """
        Returns True if ``event_name`` is registered.
        :param event_name: name of the event
        :type event_name: str
        :returns: True if registered, False otherwise
        """
        if not event_name:
            raise ValueError("event_name is empty")

        return event_name in self._events

    def register(self, event_name: str, coro: typing.Coroutine) -> None:
        """
        Register an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        :param coro: coroutine associated with ``event_name``
        :type coro: Coroutine
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not coro:
            raise ValueError("coro is empty")

        self._logger.info("Register new event: %s", repr(event_name))

        if not self.is_registered(event_name):
            self._events[event_name] = []

        self._events[event_name].append(coro)

    def unregister(self, event_name: str) -> None:
        """
        Unregister an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        self._logger.info("Unregister event: %s", repr(event_name))

        self._events.pop(event_name)

    async def fire(self, event_name: str, *args: list, **kwargs: dict) -> None:
        """
        Fire a specific event.
        :param event_name: name of the event
        :type event_name: str
        :param args: Arguments to be passed to callback functions execution.
        :type args: list
        :param kwargs: Keyword arguments to be passed to callback functions
            execution.
        :type kwargs: dict
        """
        if not event_name:
            raise ValueError("event_name is empty")

        coros = self._events.get(event_name, None)
        if not coros:
            return

        tasks = []
        for coro in coros:
            tasks.append(coro(*args, **kwargs))

        await self._tasks.put(asyncio.gather(*tasks))

    async def _consume(self) -> None:
        """
        Consume the next event.
        """
        # following await is a blocking I/O
        # so we don't need to sleep before get()
        task = await self._tasks.get()
        if not task:
            return

        # pylint: disable=broad-except
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            if "internal_error" not in self._events:
                return

            self._logger.info("Exception catched")
            self._logger.error(exc)

            coros = self._events["internal_error"]
            if len(coros) > 0:
                coro = coros[0]
                await coro(exc, coro.__name__)

    async def stop(self) -> None:
        """
        Stop the event loop.
        """
        self._logger.info("Stopping event loop")

        self._stop = True

        # indicate producer is done
        await self._tasks.put(None)

        async with self._lock:
            pass

        # consume the last tasks
        while not self._tasks.empty():
            await self._consume()

        self._logger.info("Event loop stopped")

    async def start(self) -> None:
        """
        Start the event loop.
        """
        self._stop = False

        try:
            async with self._lock:
                self._logger.info("Starting event loop")

                while not self._stop:
                    await self._consume()

                self._logger.info("Event loop completed")
        except asyncio.CancelledError:
            await self.stop()
