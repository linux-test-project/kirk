"""
.. module:: events
    :platform: Linux
    :synopsis: events handler implementation module

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import typing
import logging
import asyncio


class Event:
    """
    An event to process.
    """

    def __init__(self, ordered: bool = False) -> None:
        """
        :param ordered: True if coroutines must be processed in order
        :type ordered: bool
        """
        self._coros = []
        self._ordered = ordered

    def remove(self, coro: typing.Coroutine) -> None:
        """
        Remove a specific coroutine associated to the event.
        :param coro: coroutine to remove
        :type coro: typing.Coroutine
        """
        for item in self._coros:
            if item == coro:
                self._coros.remove(coro)
                break

    def has_coros(self) -> bool:
        """
        Check if there are still available registrations.
        """
        return len(self._coros) > 0

    def register(self, coro: typing.Coroutine) -> None:
        """
        Register a new coroutine.
        """
        self._coros.append(coro)

    def create_tasks(self, *args: list, **kwargs: dict) -> list:
        """
        Create tasks to run according to registered coroutines.
        :param args: Arguments to be passed to callback functions execution.
        :type args: list
        :param kwargs: Keyword arguments to be passed to callback functions
            execution.
        :type kwargs: dict
        """
        tasks = [coro(*args, **kwargs) for coro in self._coros]

        if self._ordered:
            return tasks

        return [asyncio.gather(*tasks)]


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

        # register a default event used to notify internal
        # errors in the our application
        self._events["internal_error"] = Event()

    def _get_event(self, name: str) -> Event:
        """
        Return an event according to its `name`.
        """
        return self._events.get(name, None)

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

        evt = self._get_event(event_name)
        if not evt:
            return False

        return evt.has_coros()

    def register(self, event_name: str, coro: typing.Coroutine, ordered: bool = False) -> None:
        """
        Register an event with ``event_name``.
        :param event_name: name of the event
        :type event_name: str
        :param coro: coroutine associated with ``event_name``
        :type coro: Coroutine
        :param ordered: if True, the event will raise coroutines in the order
            they arrive
        :type ordered: bool
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not coro:
            raise ValueError("coro is empty")

        self._logger.info("Register event: %s", repr(event_name))

        evt = self._get_event(event_name)
        if not evt:
            evt = Event(ordered=ordered)
            self._events[event_name] = evt

        evt.register(coro)

    def unregister(self, event_name: str, coro: typing.Coroutine = None) -> None:
        """
        Unregister a single event coroutine with event_name`. If `coro` is None,
        all coroutines registered will be removed.
        :param event_name: name of the event
        :type event_name: str
        :param coro: coroutine to unregister
        :type coro: typing.Coroutine
        """
        if not event_name:
            raise ValueError("event_name is empty")

        if not coro:
            raise ValueError("coro is empty")

        if not self.is_registered(event_name):
            raise ValueError(f"{event_name} is not registered")

        self._logger.info(
            "Unregister event: %s -> %s", repr(event_name), repr(coro))

        if coro:
            self._events[event_name].remove(coro)
        else:
            del self._events[event_name]

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

        evt = self._get_event(event_name)
        if not evt:
            return

        for task in evt.create_tasks(*args, **kwargs):
            await self._tasks.put(task)

    async def _consume(self) -> None:
        """
        Consume the next event.
        """
        # asyncio.queue::get() will wait until an item is available
        # without blocking the application
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

            ievt = self._get_event("internal_error")
            ievt.create_tasks(exc, task.get_name())
            if ievt:
                await asyncio.gather(*ievt)
        finally:
            self._tasks.task_done()

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
