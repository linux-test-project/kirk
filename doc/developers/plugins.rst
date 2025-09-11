.. SPDX-License-Identifier: GPL-2.0-or-later

Plugin System
=============

Sometimes, we need to cover complex testing scenarios where our System Under
Test utilizes specific protocols and infrastructures to communicate with our
host machine and execute LTP tests.

For this reason, Kirk provides a plugin system to recognize custom ``SUT``
and ``COM`` class implementations inside any external folder. These classes are
used to implement complex scenarios, and in the next sections, we will see how
to communicate with the plugin system.

To verify supported ``SUT``, please run:

.. code-block:: bash

   kirk --sut help

.. note::

   If you want to implement a new ``COM`` communication handler, please refer
   to the natively supported implementations such as ``shell.py``.

Custom System Under Test
------------------------

All the ``COM`` implementations provided by Kirk can be used to configure new
``COM`` instances used by our ``SUT``. The way we create these instances is
as follows:

.. code-block:: bash

   kirk --plugins my/folder \
        --com ssh:host=192.168.0.1:id=ssh_host0 \
        --com ssh:host=192.168.0.2:id=ssh_host1 \
        --com ssh:host=192.168.0.3:id=ssh_host2 \
        --sut mysut \
        --run-suite syscalls

We just told Kirk to create three new SSH communication handlers named
``ssh_host0``, ``ssh_host1``, and ``ssh_host2``. Each one of them has its own
host IP, and we want to use them inside ``mysut``, which is our custom ``SUT``
implementation. We will pass the folder where ``mysut`` is located to the
``--plugins`` option.

Our ``SUT`` will use our utilities to obtain the initialized objects as follows:

.. code-block:: python

    from libkirk.com import SUT

    class MySUT(SUT):
        """
        My own system under test.
        """
        _name = "mysut"

        def setup(self, **kwargs: Dict[str, str]) -> None:
            self._ssh_host0 = libkirk.com.get_com("ssh_host0")
            self._ssh_host1 = libkirk.com.get_com("ssh_host1")
            self._ssh_host2 = libkirk.com.get_com("ssh_host2")

            # and here we can start to use our SSH objects
