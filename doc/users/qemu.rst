.. SPDX-License-Identifier: GPL-2.0-or-later

Configuring a Qemu instance
===========================

To enable console on a tty device for a VM, follow these steps:

1. Open the `/etc/default/grub` file.
2. Add "console=<tty_name>, console=tty0" to the `GRUB_CMDLINE_LINUX` line.
3. Run the following command to update the GRUB configuration:

   .. code-block:: bash

       grub-mkconfig -o /boot/grub/grub.cfg

.. warning::

    Where **tty_name** should be `ttyS0`, unless you are using the virtio serial
    type. If you set the `serial=virtio` backend option, then use `hvc0` instead.
