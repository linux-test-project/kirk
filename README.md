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

The tool works out of the box by running `runkirk` script.
Minimum python requirement is 3.6+ and *optional* dependences are the following:

- `asyncssh <= 2.13.1` for SSH support
- `msgpack <= 1.0.5` for LTX support

To install `kirk` via pip, please consider the following procedure:

    # clone repository
    git clone git@github.com:acerv/kirk.git

    # create virtualenv (python-3.6+)
    virtualenv venv

    # activate virtualenv
    source venv/bin/activate

    # install kirk (add -e for development mode)
    pip install ./kirk

    # install SSH support if needed
    pip install ./kirk[ssh]

    # install LTX support if needed
    pip install ./kirk[ltx]

    # execute kirk
    kirk --help

Some basic commands are the following:

    # run LTP syscalls testing suite on host
    kirk --run-suite ltp:syscalls

    # run LTP syscalls testing suite on qemu VM
    kirk --sut qemu:image=folder/image.qcow2 \
        --run-suite ltp:syscalls

    # run LTP syscalls testing suite via SSH
    kirk --sut=ssh:host myhost.com:user=root:key_file=myhost_id_rsa \
        --run-suite ltp:syscalls

    # run LTP syscalls testing suite in parallel on host using 16 workers
    kirk --run-suite ltp:syscalls --workers 16

    # run LTP syscalls testing suite in parallel via SSH using 16 workers
    kirk --sut=ssh:host myhost.com:user=root:key_file=myhost_id_rsa \
        --run-suite ltp:syscalls --workers 16

It's possible to run a single command before running testing suites using
`--run-command` option as following:

    kirk --run-command /mnt/setup.sh \
        --sut qemu:image=folder/image.qcow2:virtfs=/home/user/tests \
        --run-suite ltp:syscalls

Every session has a temporary directory that can be found in
`/<TMPDIR>/kirk-of<username>`. Inside this folder there's a symlink
called `latest`, pointing to the latest session's temporary directory.

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
class implementations inside the `kirk` package folder. Please check `host.py`
or `ssh.py` implementations for more details.

Once a new SUT class is implemented and placed inside the `kirk` package folder,
`kirk -s help` command can be used to see if application correctly
recognise it.

Implementing Framework
======================

Every testing framework has it's own setup, defining tests folders, data and
variables. For this reason, `Framework` class provides a generic API that, once
implemented, permits to define a specific testing framework. The class 
implementation must be included inside the `kirk` library folder and it will be
used as an abstraction layer between `kirk` scheduler and the specific testing
framework.

Development
===========

The application is validated using `pytest` and `pylint`.
To run unittests:

    pytest

To run linting checks:

    pylint --rcfile=pylint.ini ./ltp
