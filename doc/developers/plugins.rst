.. SPDX-License-Identifier: GPL-2.0-or-later

Plugin System
=============

Sometimes, we need to cover complex testing scenarios where our System Under
Test utilizes specific protocols and infrastructures to communicate with our
host machine and execute LTP tests.

For this reason, Kirk provides a plugin system to recognize custom ``SUT``
and ``ComChannel`` class implementations inside any external folder. These
classes are used to implement complex scenarios, and in the next sections, we
will see how to communicate with the plugin system.

To verify supported ``SUT``, please run:

.. code-block:: bash

   kirk --sut help

.. note::

   If you want to implement a new ``ComChannel`` communication handler, please
   refer to the natively supported implementations such as ``shell.py``.

Custom System Under Test
------------------------

All the channels implementations provided by kirk can be used or duplicated to
use them inside our ``SUT``. The way we create these instances is as follows:

.. code-block:: bash

   kirk --plugins my/plugins/folder \
        --com ssh:host=192.168.0.1:id=ssh_host0 \
        --sut mysut \
        --run-suite syscalls

We just created a SSH channel ``ssh_host0`` that can be used by ``mysut``
implementation in order to setup testing.

Our ``SUT`` can now use the ``libkirk.com.get_channels()`` utility to read
available channels and get the one we need, as follows:

.. code-block:: python

   def setup(self, **kwargs: Dict[str, Any]) -> None:
       self._ssh = next(
           (c for in libkirk.com.get_channels() if c.name == "ssh_host0"),
           None,
       )

But remember that **only one** channel must be given back to kirk in order to
communicate with the System Under Test via ``get_channel()`` API.

.. code-block:: python

   def get_channel() -> ComChannel:
      return self._ssh

Practical example
-----------------

We might want to test LTP inside an embedded system on our desk via SSH.
We have two scripts to run before communicating with the SUT:

- ``install_firmware.sh`` to install a new firmware
- ``reboot_board.sh`` to reboot board if it's not responding anymore

The idea is that we install a new firmware before running tests, run tests and
if system breaks/panic/timeout, we reboot it, continuing testing suite from
where we left.

We can easily achieve this scenario with the following implementation:

.. code-block:: python

    import os
    from typing import Dict, Optional

    import libkirk.com
    from libkirk.com import ComChannel, IOBuffer
    from libkirk.errors import SUTError
    from libkirk.sut import SUT


    class EmbeddedSUT(SUT):
        # This is needed by kirk to know what is the name of the SUT
        # we are implementing
        _name = "embedded"

        def __init__(self) -> None:
            self._ssh = None
            self._shell = None

            currdir = os.path.dirname(os.path.realpath(__file__))
            self._install_sh = os.path.join(currdir, "install_firmware.sh")
            self._reboot_sh = os.path.join(currdir, "reboot_board.sh")

        def setup(self, **kwargs: Dict[str, str]) -> None:
            # Here we fetch all data we need. At this point we know that kirk
            # already initialized all communication channels
            chan_name = kwargs.get("com", "ssh")

            self._ssh = next(
                (c for c in libkirk.com.get_channels() if c.name == chan_name), None
            )
            self._shell = next(
                (c for c in libkirk.com.get_channels() if c.name == "shell"), None
            )

            if not self._ssh:
                raise SUTError(f"Can't find channel '{chan_name}'")

        @property
        def config_help(self) -> Dict[str, str]:
            # Parameters to setup our SUT
            return {
                "com": "Communication channel (default: ssh)",
            }

        def get_channel(self) -> ComChannel:
            # Here we return our main communication channel
            return self._ssh

        async def start(self, iobuffer: Optional[IOBuffer] = None) -> None:
            # Initialize the SUT by running commands, scripts and everything
            # that can be done via our communication channels
            if await self.is_running:
                return

            await self._shell.ensure_communicate(iobuffer=iobuffer)

            ret = await self._shell.run_command(self._install_sh, iobuffer=iobuffer)
            if ret["returncode"] != 0:
                raise SUTError(f"{self._install_sh} failed")

            await self._ssh.ensure_communicate(iobuffer=iobuffer)

        async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
            # Stop any operation in our SUT. This can be requires in any moment
            # during tests run
            if not await self.is_running:
                return

            await self._ssh.stop(iobuffer=iobuffer)

        async def restart(self, iobuffer: Optional[IOBuffer] = None) -> None:
            # Stop any operation in our SUT and restart the system
            await self.stop(iobuffer=iobuffer)

            ret = await self._shell.run_command(self._reboot_sh, iobuffer=iobuffer)
            if ret["returncode"] != 0:
                raise SUTError(f"{self._reboot_sh} failed")

            await self._shell.stop(iobuffer=iobuffer)
            await self.start(iobuffer=iobuffer)

        @property
        async def is_running(self) -> bool:
            # Tell kirk when SUT is operating or not
            return await self._ssh.active


Let's suppose we have a ``$HOME/plugins`` folder where we placed our
``EmbeddedSUT`` implementation and its scripts. Then we can run ``syscalls``
testing suite with kirk as following:

.. code-block:: python

    kirk --plugins $HOME/plugins \
        --sut embedded \
        --com ssh:host=192.168.0.1:user=root:key_file=/home/user/.ssh/id_rsa \
        --run-suite syscalls
