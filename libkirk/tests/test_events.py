"""
Unittest for events module.
"""

import asyncio

import pytest

import libkirk


@pytest.fixture(autouse=True)
def cleanup():
    """
    Cleanup all events after each test.
    """
    yield
    libkirk.events.reset()


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
        libkirk.events.register(None, funct)

    with pytest.raises(ValueError):
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
        libkirk.events.unregister("", None)

    with pytest.raises(ValueError):
        libkirk.events.unregister("not_registered", None)


def test_unregister_entire_event():
    """
    Test unregister method removing the entire event entry.
    """

    async def funct():
        pass

    libkirk.events.register("myevent", funct)
    assert libkirk.events.is_registered("myevent")

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


async def test_fire_handler_exception():
    """
    Test that exceptions in event handlers are caught and forwarded
    to the internal_error event.
    """
    errors = []

    async def bad_handler():
        raise RuntimeError("test error")

    async def error_catcher(error, name):
        errors.append(error)

    async def start():
        await libkirk.events.start()

    libkirk.events.register("bad_event", bad_handler)
    libkirk.events.register("internal_error", error_catcher)

    libkirk.create_task(start())

    await libkirk.events.fire("bad_event")

    while not errors:
        await asyncio.sleep(1e-3)

    await libkirk.events.stop()

    assert len(errors) == 1
    assert isinstance(errors[0][0], RuntimeError)


async def test_fire():
    """
    Test fire method.
    """
    times = 100
    called = []

    async def diehard(error, name):
        assert error is not None
        assert name is not None

    async def tofire(param):
        called.append(param)

    async def start():
        await libkirk.events.start()

    async def run():
        for i in range(times):
            await libkirk.events.fire("myevent", i)

        while len(called) < times:
            await asyncio.sleep(1e-3)

        await libkirk.events.stop()

    libkirk.events.register("myevent", tofire)
    assert libkirk.events.is_registered("myevent")

    libkirk.events.register("internal_error", diehard)
    assert libkirk.events.is_registered("internal_error")

    libkirk.create_task(start())
    await run()

    while len(called) < times:
        asyncio.sleep(1e-3)

    called.sort()
    for i in range(times):
        assert called[i] == i
