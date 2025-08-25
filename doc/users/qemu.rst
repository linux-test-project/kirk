.. SPDX-License-Identifier: GPL-2.0-or-later

Configuring a Qemu instance
===========================

To enable console on a tty device for a VM, follow these steps:

* open the ``/etc/default/grub`` file.
* add ``console=ttyS0,console=tty0`` to the ``GRUB_CMDLINE_LINUX`` line.
* run the following command to update the GRUB configuration:

   .. code-block:: bash

       grub-mkconfig -o /boot/grub/grub.cfg

.. warning::

    If you set the ``serial=virtio`` backend option, then use ``hvc0`` instead.
