.. SPDX-License-Identifier: GPL-2.0-or-later

What is Kirk?
=============

Kirk application is a fork of `runltp-ng <https://github.com/linux-test-project/runltp-ng>`_
and it's the official `LTP <https://github.com/linux-test-project>`_ tests
executor. It provides support for remote testing via Qemu, SSH, LTX, parallel
execution and much more.

.. WARNING::

   The `master` branch might be affected by breaking changes. Make sure to use
   one of the `latest <https://github.com/linux-test-project/kirk/tags>`_
   available versions.

.. code-block:: bash

    Host information
            Hostname:   susy
            Python:     3.8.20 (default, Oct  2 2024, 16:34:12) [Clang 18.1.8 ]
            Directory:  /tmp/kirk.acer/tmp1bm7xllh

    Connecting to SUT: default

    Suite: math
    ───────────
    abs01: pass  (0.001s)
    atof01: pass  (0.001s)
    float_bessel: pass  (0.359s)
    float_exp_log: pass  (0.315s)
    float_iperb: pass  (0.116s)
    float_power: pass  (0.262s)
    float_trigo: pass  (0.287s)
    fptest01: pass  (0.002s)
    fptest02: pass  (0.002s)
    nextafter01: pass  (0.001s)

    Execution time: 1.515s

    Disconnecting from SUT: default

    Target information
    ──────────────────
    Kernel:   Linux 6.12.0-160000.9-default #1 SMP PREEMPT_DYNAMIC Fri Jan 16 09:29:05 UTC 2026 (9badd3c)
    Cmdline:  BOOT_IMAGE=/boot/vmlinuz-6.12.0-160000.9-default
              root=UUID=7df22dee-1273-4a53-8f83-95ba6c000e39
              resume=UUID=2c0196fa-686c-455d-98d5-641c5ecbf57f
              mitigations=auto
              quiet
              security=selinux
              selinux=1
    Machine:  x86_64
    Arch:     x86_64
    RAM:      61346668 kB
    Swap:     2081088 kB
    Distro:   opensuse-leap 16.0

    ────────────────────────
          TEST SUMMARY
    ────────────────────────
    Suite:   math
    Runtime: 1.345s
    Runs:    10

    Results:
        Passed:   22
        Failed:   0
        Broken:   0
        Skipped:  0
        Warnings: 0

    Session stopped

Some references:

* `Documentation <https://kirk.readthedocs.io/en/latest/>`_
* `Source code <https://github.com/linux-test-project/kirk>`_
* `Releases <https://github.com/linux-test-project/kirk/releases>`_
