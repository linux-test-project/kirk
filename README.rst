.. SPDX-License-Identifier: GPL-2.0-or-later

What is Kirk?
=============

Kirk application is a fork of `runltp-ng <https://github.com/linux-test-project/runltp-ng>`_
and it's the official `LTP <https://github.com/linux-test-project>`_ tests
executor. It provides support for remote testing via Qemu, SSH, LTX, parallel
execution and much more.

.. code-block:: bash

    Host information

            Hostname:   susy
            Python:     3.6.15 (default, Sep 23 2021, 15:41:43) [GCC]
            Directory:  /tmp/kirk.acer/tmp1n8pa6gy

    Connecting to SUT: host

    Starting suite: math
    ---------------------
    abs01: pass  (0.003s)
    atof01: pass  (0.004s)
    float_bessel: pass  (1.174s)
    float_exp_log: pass  (1.423s)
    float_iperb: pass  (0.504s)
    float_power: pass  (1.161s)
    float_trigo: pass  (1.208s)
    fptest01: pass  (0.006s)
    fptest02: pass  (0.004s)
    nextafter01: pass  (0.001s)

    Execution time: 5.895s

            Suite:       math
            Total runs:  10
            Runtime:     5.488s
            Passed:      22
            Failed:      0
            Skipped:     0
            Broken:      0
            Warnings:    0
            Kernel:      Linux 6.4.0-150600.23.50-default
            Machine:     x86_64
            Arch:        x86_64
            RAM:         15573156 kB
            Swap:        2095424 kB
            Distro:      opensuse-leap 15.6

    Disconnecting from SUT: host

Some references:

* `Documentation <https://kirk.readthedocs.io/en/latest/>`_
* `Source code <https://github.com/linux-test-project/kirk>`_
* `Releases <https://github.com/linux-test-project/kirk/releases>`_
