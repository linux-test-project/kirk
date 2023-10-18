What is Kirk?
=============

Kirk application is a fork of [runltp-ng](https://github.com/linux-test-project/runltp-ng)
and it aims to merge multiple Linux testing frameworks in one tool, providing
support for remote testing via Qemu, SSH, LTX, parallel execution and much more.

    Host information

            System: Linux
            Node: susy
            Kernel Release: 5.14.21-150400.24.60-default
            Kernel Version: #1 SMP PREEMPT_DYNAMIC Wed Apr 12 12:13:32 UTC 2023 (93dbe2e)
            Machine Architecture: x86_64
            Processor: x86_64

            Temporary directory: /tmp/kirk.acer/tmpz49sip95

    Connecting to SUT: host
    Starting suite: math
    abs01: pass | tainted  (0.001s)
    atof01: pass | tainted  (0.002s)
    float_bessel: pass | tainted  (0.673s)
    float_exp_log: pass | tainted  (0.667s)
    float_iperb: pass | tainted  (0.252s)
    float_power: pass | tainted  (0.562s)
    float_trigo: pass | tainted  (0.646s)
    fptest01: pass | tainted  (0.002s)
    fptest02: pass | tainted  (0.003s)
    nextafter01: pass | tainted  (0.002s)

    Suite Name: math
    Total Run: 10
    Elapsed Time: 3.039s
    Passed Tests: 22
    Failed Tests: 0
    Skipped Tests: 0
    Broken Tests: 0
    Warnings: 0
    Kernel Version: Linux 5.14.21-150400.24.60-default #1 SMP PREEMPT_DYNAMIC Wed Apr 12 12:13:32 UTC 2023 (93dbe2e)
    CPU: x86_64
    Machine Architecture: x86_64
    RAM: 15569424 kB
    Swap memory: 2095424 kB
    Distro: opensuse-leap
    Distro Version: 15.4


    Disconnecting from SUT: host


Quickstart
==========

The tool works out of the box by running `kirk` script.
Minimum python requirement is 3.6+ and *optional* dependences are the following:

- [asyncssh](https://pypi.org/project/asyncssh/) for SSH support
- [msgpack](https://pypi.org/project/msgpack/) for LTX support

`kirk` will detect if dependences are installed and activate the corresponding
support. If no dependences are provided by the OS's package manager,
`virtualenv` can be used to install them:

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

    # run LTP syscalls testing suite on host
    ./kirk --framework ltp --run-suite syscalls

    # run LTP syscalls testing suite on qemu VM
    ./kirk --framework ltp \
        --sut qemu:image=folder/image.qcow2:user=root:password=root \
        --run-suite syscalls

    # run LTP syscalls testing suite via SSH
    ./kirk --framework ltp \
        --sut ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
        --run-suite syscalls

    # run LTP syscalls testing suite in parallel on host using 16 workers
    ./kirk --framework ltp --run-suite syscalls --workers 16

    # run LTP syscalls testing suite in parallel via SSH using 16 workers
    ./kirk --framework ltp \
        --sut ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
        --run-suite syscalls --workers 16

It's possible to run a single command before running testing suites using
`--run-command` option as following:

    ./kirk --framework ltp \
        --run-command /mnt/setup.sh \
        --sut qemu:image=folder/image.qcow2:virtfs=/home/user/tests:user=root:password=root \
        --run-suite syscalls

Every session has a temporary directory that can be found in
`/<TMPDIR>/kirk.<username>`. Inside this folder there's a symlink
called `latest`, pointing to the latest session's temporary directory.

In certain cases, `kirk` sessions can be restored. This can be really helpful
when we need to restore the last session after a system crash:

    # restore the latest session
    ./kirk --framework ltp \
        --restore /tmp/kirk.<username>/latest \
        --run-suite syscalls

Setting up console for Qemu
===========================

To enable console on a tty device for a VM do:

* open `/etc/default/grub`
* add `console=$tty_name, console=tty0` to `GRUB_CMDLINE_LINUX`
* run `grub-mkconfig -o /boot/grub/grub.cfg`

Where `$tty_name` should be `ttyS0`, unless virtio serial type is used (i.e.
if you set the `serial=virtio` backend option, then use `hvc0`)

Implementing SUT
================

Sometimes we need to cover complex testing scenarios, where the SUT uses
particular protocols and infrastructures, in order to communicate with our
host machine and to execute tests binaries.

For this reason, `kirk` provides a plugin system to recognize custom SUT
class implementations inside the `libkirk` folder. Please check `host.py`
or `ssh.py` implementations for more details.

Once a new SUT class is implemented and placed inside the `libkirk` folder,
`kirk -s help` command can be used to see if application correctly
recognise it.

Implementing Framework
======================

Every testing framework has it's own setup, defining tests folders, data and
variables. For this reason, `Framework` class provides a generic API that, once
implemented, permits to define a specific testing framework. The class 
implementation must be included inside the `libkirk` folder and it will be
used as an abstraction layer between `kirk` scheduler and the specific testing
framework.

Development
===========

The application is validated using `pytest` and `pylint`.
To run unittests:

    pytest

To run linting checks:

    pylint --rcfile=pylint.ini ./libkirk
