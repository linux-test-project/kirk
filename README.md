What is Kirk?
=============

Kirk application is a fork of [runltp-ng](https://github.com/linux-test-project/runltp-ng)
and it's the official [LTP](https://github.com/linux-test-project) tests
executor. It provides support for remote testing via Qemu, SSH, LTX, parallel
execution and much more.

```bash
Host information

        Hostname:   susy
        Python:     3.6.15 (default, Sep 23 2021, 15:41:43) [GCC]
        Directory:  /tmp/kirk.acer/tmpw4hr1wla

Connecting to SUT: host

Starting suite: math
abs01: pass (0.012s)
atof01: pass (0.005s)
float_bessel: pass (1.154s)
float_exp_log: pass (1.392s)
float_iperb: pass (0.508s)
float_power: pass (1.158s)
float_trigo: pass (1.189s)
fptest01: pass (0.013s)
fptest02: pass (0.007s)
nextafter01: pass (0.002s)

Execution time: 5.939s

        Suite:       math
        Total runs:  10
        Runtime:     5.441s
        Passed:      22
        Failed:      0
        Skipped:     0
        Broken:      0
        Warnings:    0
        Kernel:      Linux 6.4.0-150600.23.50-default
        Machine:     x86_64
        Arch:        x86_64
        RAM:         15573136 kB
        Swap:        2095424 kB
        Distro:      opensuse-leap 15.6

Disconnecting from SUT: host
```

Quickstart
----------

The tool works out of the box by running `kirk` script.
Minimum python requirement is 3.6+ and *optional* dependences are the following:

- [asyncssh](https://pypi.org/project/asyncssh/) for SSH support
- [msgpack](https://pypi.org/project/msgpack/) for LTX support

`kirk` will detect if dependences are installed and activate the corresponding
support. If no dependences are provided by the OS's package manager,
`virtualenv` can be used to install them:

```bash
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
```

Some basic commands are the following:

```bash
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
```

It's possible to run a single command before running testing suites using
`--run-command` option as following:

```bash
./kirk --run-command /mnt/setup.sh \
       --sut qemu:image=folder/image.qcow2:virtfs=/home/user/tests:user=root:password=root \
       --run-suite syscalls
```

Every session has a temporary directory that can be found in
`/<TMPDIR>/kirk.<username>`. Inside this folder there's a symlink
called `latest`, pointing to the latest session's temporary directory.

In certain cases, `kirk` sessions can be restored. This can be really helpful
when we need to restore the last session after a system crash:

```bash
# restore the latest session
./kirk --restore /tmp/kirk.<username>/latest --run-suite syscalls
```

Setting up console for Qemu
---------------------------

To enable console on a tty device for a VM do:

- open `/etc/default/grub`
- add `console=$tty_name, console=tty0` to `GRUB_CMDLINE_LINUX`
- run `grub-mkconfig -o /boot/grub/grub.cfg`

Where `$tty_name` should be `ttyS0`, unless virtio serial type is used (i.e.
if you set the `serial=virtio` backend option, then use `hvc0`)

Implementing SUT
----------------

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
----------------------

Every testing framework has it's own setup, defining tests folders, data and
variables. For this reason, `Framework` class provides a generic API that, once
implemented, permits to define a specific testing framework. The class 
implementation must be included inside the `libkirk` folder and it will be
used as an abstraction layer between `kirk` scheduler and the specific testing
framework.

Development
-----------

The application is validated using `pytest` and `pylint`.
To run unittests:

```bash
pytest
```

To run linting checks:

```bash
pylint --rcfile=pylint.ini ./libkirk
```
