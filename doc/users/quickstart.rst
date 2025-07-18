.. SPDX-License-Identifier: GPL-2.0-or-later

Start using kirk
================

The tool works out of the box by running `kirk` script.
Minimum python requirement is 3.6+ and *optional* dependences are the following:

- `asyncssh <https://pypi.org/project/asyncssh/>`_ for SSH support
- `msgpack <https://pypi.org/project/msgpack/>`_ for LTX support

`kirk` will detect if dependences are installed and activate the corresponding
support. If no dependences are provided by the OS's package manager,
`virtualenv` can be used to install them:

.. code-block:: bash

    # download source code
    git clone git@github.com:acerv/kirk.git
    cd kirk

    # create your virtual environment (python-3.6+)
    virtualenv .venv

    # activate virtualenv
    source .venv/bin/activate

    # SSH support
    pip install asyncssh

    # LTX support
    pip install msgpack

    # run kirk
    ./kirk --help

Some basic commands are the following:

.. code-block:: bash

    # run LTP syscalls testing suite on host
    ./kirk --run-suite syscalls

    # run LTP syscalls testing suite on qemu VM
    ./kirk --sut qemu:image=folder/image.qcow2:user=root:password=root \
           --run-suite syscalls

    # run LTP syscalls testing suite via SSH
    ./kirk --sut ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
           --run-suite syscalls

    # run LTP syscalls testing suite in parallel on host using 16 workers
    ./kirk --run-suite syscalls --workers 16

    # run LTP syscalls testing suite in parallel via SSH using 16 workers
    ./kirk --sut ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
           --run-suite syscalls --workers 16

    # pass environment variables (list of key=value separated by ':')
    ./kirk --run-suite net.features \
           --env 'VIRT_PERF_THRESHOLD=180:LTP_NET_FEATURES_IGNORE_PERFORMANCE_FAILURE=1'

It's possible to run a single command before running testing suites using
`--run-command` option as following:

.. code-block:: bash

    ./kirk --run-command /mnt/setup.sh \
           --sut qemu:image=folder/image.qcow

