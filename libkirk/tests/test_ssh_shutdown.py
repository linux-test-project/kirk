"""
SSH shutdown races without a remote server.
"""

import asyncio
from unittest.mock import Mock

import pytest

from libkirk.channels.ssh import SSHComChannel
import libkirk


@pytest.mark.parametrize("command_finishes_first", [False, True])
async def test_stop_parallel_commands(monkeypatch, command_finishes_first):
    pytest.importorskip("asyncssh")
    release = asyncio.Event()

    class Channel:
        def __init__(self):
            self.started = asyncio.Event()
            self.killed = asyncio.Event()
            self.finished = asyncio.Event()
            self.waits = 0

        def kill(self):
            self.killed.set()

        async def wait_closed(self):
            self.waits += 1
            if self.waits == 1:
                self.started.set()
                await self.killed.wait()
                if not command_finishes_first:
                    await release.wait()
            elif command_finishes_first:
                await self.finished.wait()

        def get_returncode(self):
            return -9

    channels = [Channel(), Channel()]
    session = Mock()
    session.kernel_panic.return_value = False
    session.get_output.return_value = []

    async def create_session(factory, command, **kwargs):
        return channels[int(command)], session

    async def wait_closed():
        pass

    connection = Mock()
    connection.create_session = create_session
    connection.wait_closed = wait_closed
    com = SSHComChannel()
    monkeypatch.setattr(com, "_conn", connection)
    monkeypatch.setattr(com, "_session_sem", asyncio.Semaphore(2))

    tasks = []
    for index, channel in enumerate(channels):
        task = libkirk.create_task(com.run_command(str(index)))
        task.add_done_callback(lambda task, channel=channel: channel.finished.set())
        tasks.append(task)

    try:
        await asyncio.wait_for(
            asyncio.gather(*(channel.started.wait() for channel in channels)), 5
        )
        await asyncio.wait_for(com.stop(), 5)
        assert all(channel.killed.is_set() for channel in channels)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
        assert [result["returncode"] for result in results] == [-9, -9]
        assert com._channels == []
        assert not await com.active()
        connection.close.assert_called_once_with()
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
