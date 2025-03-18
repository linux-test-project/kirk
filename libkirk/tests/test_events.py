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


def test_unregister_errors():
    """
    Test unregister method during errors.
    """
    with pytest.raises(ValueError):
        libkirk.events.unregister(None)


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


@pytest.mark.asyncio
async def test_fire_errors():
    """
    Test fire method during errors.
    """
    with pytest.raises(ValueError):
        await libkirk.events.fire(None, "prova")


@pytest.mark.asyncio
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
