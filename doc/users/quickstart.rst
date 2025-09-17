.. SPDX-License-Identifier: GPL-2.0-or-later

Start using kirk
================

The tool works out of the box by running ``kirk`` script.
Minimum python requirement is 3.6+ and *optional* dependences are the following:

- `asyncssh <https://pypi.org/project/asyncssh/>`_ for SSH support
- `msgpack <https://pypi.org/project/msgpack/>`_ for LTX support

kirk will detect if dependences are installed and activate the corresponding
support.

To use kirk via git repository:

.. code-block:: bash

    git clone git@github.com:acerv/kirk.git
    export PATH=$PATH:$PWD/kirk

    kirk --help

kirk is also present in `pypi <https://pypi.org/project/kirk>`_ and it can be
installed via ``pip`` command:

.. code-block:: bash

   pip install --user kirk

Some basic commands are the following:

.. code-block:: bash

    # run LTP syscalls testing suite on host
    kirk --run-suite syscalls

    # run LTP syscalls testing suite on qemu VM
    kirk --com qemu:image=folder/image.qcow2:user=root:password=root \
         --sut default:com=qemu \
         --run-suite syscalls

    # run LTP syscalls testing suite via SSH
    kirk --com ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
         --sut default:com=ssh \
         --run-suite syscalls

    # run LTP syscalls testing suite in parallel on host using 16 workers
    kirk --run-suite syscalls --workers 16

    # run LTP syscalls testing suite in parallel via SSH using 16 workers
    kirk --com ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
         --sut default:com=ssh \
         --run-suite syscalls --workers 16

    # pass environment variables (list of key=value separated by ':')
    kirk --run-suite net.features \
         --env 'VIRT_PERF_THRESHOLD=180:LTP_NET_FEATURES_IGNORE_PERFORMANCE_FAILURE=1'

It's possible to run a single command before running testing suites using
``--run-command`` option as following:

.. code-block:: bash

    kirk --run-command ./setup_sut.sh \
           --com qemu:image=folder/image.qcow \
           --sut default:com=qemu

