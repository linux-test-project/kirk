"""
Unittest for events module.
"""

import asyncio

import pytest

import libkirk


def test_reset():
    """
    Test reset method.
    """

    async def funct():
        pass

    libkirk.events.register("myevent", funct)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.reset()
    assert not libkirk.events.is_registered("myevent")


def test_register_errors():
    """
    Test register method during errors.
    """

    async def funct():
        pass

    with pytest.raises(ValueError):
        # pyrefly: ignore[bad-argument-type]
        libkirk.events.register(None, funct)

    with pytest.raises(ValueError):
        # pyrefly: ignore[bad-argument-type]
        libkirk.events.register("myevent", None)


def test_register():
    """
    Test register method.
    """

    async def funct():
        pass

    libkirk.events.register("myevent", funct)
    assert libkirk.events.is_registered("myevent")


def test_unregister_all():
    """
    Test unregister method removing all coroutine
    from the events list.
    """

    async def funct1():
        pass

    async def funct2():
        pass

    assert not libkirk.events.is_registered("myevent")

    # register events first
    libkirk.events.register("myevent", funct1)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.register("myevent", funct2)
    assert libkirk.events.is_registered("myevent")

    # unregister events one by one
    libkirk.events.unregister("myevent", funct1)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.unregister("myevent", funct2)
    assert not libkirk.events.is_registered("myevent")


def test_unregister_single():
    """
    Test unregister method removing a single coroutine
    from the events list.
    """

    async def funct():
        pass

    libkirk.events.register("myevent", funct)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.unregister("myevent", funct)
    assert not libkirk.events.is_registered("myevent")


async def test_fire_errors():
    """
    Test fire method during errors.
    """
    with pytest.raises(ValueError):
        # pyrefly: ignore[bad-argument-type]
        await libkirk.events.fire(None, "prova")


def test_is_registered_empty_name():
    """
    Test is_registered with empty name.
    """
    with pytest.raises(ValueError):
        libkirk.events.is_registered("")


def test_unregister_errors():
    """
    Test unregister method during errors.
    """
    with pytest.raises(ValueError):
        # pyrefly: ignore[bad-argument-type]
        libkirk.events.unregister("", None)

    with pytest.raises(ValueError):
        # pyrefly: ignore[bad-argument-type]
        libkirk.events.unregister("not_registered", None)


def test_unregister_entire_event():
    """
    Test unregister method removing the entire event entry.
    """

    async def funct():
        pass

    libkirk.events.register("myevent", funct)
    assert libkirk.events.is_registered("myevent")

    # pyrefly: ignore[bad-argument-type]
    libkirk.events.unregister("myevent", None)
    assert not libkirk.events.is_registered("myevent")


def test_event_remove_nonexistent():
    """
    Test Event.remove() with a coro that was never registered.
    """
    from libkirk.evt import Event

    event = Event()
    # should not raise
    event.remove(lambda: None)


async def test_fire_handler_exception(run_events):
    """
    Test that exceptions in event handlers are caught and forwarded
    to the internal_error event.
    """
    errors = []
    received = asyncio.Event()

    async def bad_handler():
        raise RuntimeError("test error")

    async def error_catcher(error, name):
        errors.append(error)
        received.set()

    libkirk.events.register("bad_event", bad_handler)
    libkirk.events.register("internal_error", error_catcher)

    await libkirk.events.fire("bad_event")
    await asyncio.wait_for(received.wait(), timeout=5)

    assert len(errors) == 1
    assert isinstance(errors[0][0], RuntimeError)


async def test_fire(run_events):
    """
    Test fire method.
    """
    times = 100
    called = []
    errors = []
    completed = asyncio.Event()

    async def diehard(error, name):
        errors.append((error, name))

    async def tofire(param):
        called.append(param)
        if len(called) == times:
            completed.set()

    libkirk.events.register("myevent", tofire)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.register("internal_error", diehard)
    assert libkirk.events.is_registered("internal_error")

    for i in range(times):
        await libkirk.events.fire("myevent", i)

    await asyncio.wait_for(completed.wait(), timeout=5)
    assert sorted(called) == list(range(times))
    assert errors == []
