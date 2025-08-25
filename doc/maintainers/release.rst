.. SPDX-License-Identifier: GPL-2.0-or-later

Setting up a new release
========================

These are the steps which need to be completed before a new release:

* bump ``libkirk.__version__`` variable to the new kirk version
* verify that CI has been completed and passing after pushing
* manually test Qemu support via ``libkirk/tests/test_qemu.py``
* create a package via ``python -m build`` command
* push package in pypi via ``twine upload dist/kirk-<version>.tar.gz`` command
