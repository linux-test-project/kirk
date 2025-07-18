.. SPDX-License-Identifier: GPL-2.0-or-later

Implementing a new SUT
======================

Sometimes we need to cover complex testing scenarios, where the SUT
(System Under Test) uses particular protocols and infrastructures to
communicate with our host machine and execute test binaries.

For this reason, `kirk` provides a plugin system to recognize custom SUT class
implementations inside the `libkirk` folder. Please check the `host.py` or
`ssh.py` implementations for more details.

Once a new SUT class is implemented and placed inside the `libkirk` folder, you
can use the following command to see if the application correctly recognizes it:

.. code-block:: bash

    kirk -s help

