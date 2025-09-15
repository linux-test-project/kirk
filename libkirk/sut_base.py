"""
.. module:: sut_base
    :platform: Linux
    :synopsis: module implementing a generic SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

from typing import Any, Dict, Optional

import libkirk.com
import libkirk.types
from libkirk.com import ComChannel, IOBuffer
from libkirk.errors import SUTError
from libkirk.sut import SUT


class GenericSUT(SUT):
    """
    Generic SUT which is defining a structure to start implementing it.

    This class can be inherited in order to provide all its features also to
    the new implementations. Used by itself, it's just a SUT named 'default'
    for the kirk application and it's recognized by the plugin system.
    """

    def __init__(self) -> None:
        self._com = None

    def setup(self, **kwargs: Dict[str, Any]) -> None:
        com_name = libkirk.types.dict_item(kwargs, "com", str, "shell")
        if not com_name:
            raise SUTError("Communication channel has not been defined")

        channels = libkirk.com.get_channels()
        if not channels:
            raise SUTError("No communication channels are provided")

        com = next((c for c in channels if c.name == com_name), None)
        if not com:
            raise SUTError(f"Can't find communication channel '{com_name}'")

        # pyrefly: ignore[bad-assignment]
        self._com = com

    @property
    def config_help(self) -> Dict[str, str]:
        return {
            "com": "Communication channel name (default: shell)",
        }

    @property
    def name(self) -> str:
        return "default"

    def get_channel(self) -> ComChannel:
        if not self._com:
            raise SUTError("SUT is not initialized")

        return self._com

    async def start(self, iobuffer: Optional[IOBuffer] = None) -> None:
        if await self.is_running:
            return

        await self.get_channel().ensure_communicate(iobuffer)

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        if not await self.is_running:
            return

        await self.get_channel().stop(iobuffer)

    async def restart(self, iobuffer: Optional[IOBuffer] = None) -> None:
        await self.stop(iobuffer)
        await self.start(iobuffer)

    @property
    async def is_running(self) -> bool:
        return await self.get_channel().active
