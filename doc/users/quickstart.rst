.. SPDX-License-Identifier: GPL-2.0-or-later

Start using kirk
================

Installation
------------

kirk is available on `PyPI <https://pypi.org/project/kirk>`_ and can be
installed using ``pip``:

.. code-block:: bash

    pip install --user kirk

To include optional features such as SSH or LTX:

.. code-block:: bash

    pip install --user 'kirk[ssh,ltx]'

To install from the git repository:

.. code-block:: bash

    git clone https://github.com/linux-test-project/kirk.git
    cd kirk
    pip install .

Basic usage
-----------

Run the LTP ``syscalls`` test suite on the host:

.. code-block:: bash

    kirk --run-suite syscalls

Run tests in parallel using 16 workers:

.. code-block:: bash

    kirk --run-suite syscalls --workers 16

Pass environment variables for LTP tests from the shell:

.. code-block:: bash

    LTP_NET_FEATURES_IGNORE_PERFORMANCE_FAILURE=1 \
    kirk --run-suite net.features

Run a custom command before executing the test suite:

.. code-block:: bash

    kirk --run-command ./setup_sut.sh \
         --run-suite syscalls

Run a subset of tests using sharding (e.g., shard 1 of 4):

.. code-block:: bash

    kirk --run-suite syscalls --shard 1/4

Optional features
-----------------

Kirk requires Python 3.6+ and works out of the box for host execution.
Optional features are automatically detected when dependencies are installed:

* :doc:`ssh`: Remote execution via SSH (requires `asyncssh <https://pypi.org/project/asyncssh/>`_)
* :doc:`ltx`: Remote execution via LTX (requires `msgpack <https://pypi.org/project/msgpack/>`_)
* :doc:`qemu`: Virtual machine testing via QEMU
