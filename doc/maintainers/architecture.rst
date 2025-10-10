.. SPDX-License-Identifier: GPL-2.0-or-later

Internal architecture
=====================

.. warning::

   The internal architecture might change over time.

Overview
--------

.. graphviz::
   
   digraph {
      newrank=true;

      subgraph cluster_0 {
         label = "Scheduler";
         labeljust = "l";

         SuiteScheduler;
         TestScheduler;

         SuiteScheduler -> TestScheduler;
      }

      subgraph cluster_1 {
         label = "Communication";
         labeljust = "l";

         ComChannel;
         ShellComChannel;
         LTXComChannel;
         QemuComChannel;
         SSHComChannel;

         ComChannel -> ShellComChannel;
         ComChannel -> LTXComChannel;
         ComChannel -> QemuComChannel;
         ComChannel -> SSHComChannel;
      }

      subgraph cluster_2 {
         label = "Framework";
         labeljust = "r";

         LTPFramework;
      }

      subgraph cluster_3 {
         label = "SUT";
         labeljust = "l";

         GenericSUT;
      }

      {
         rank=same;
         SuiteScheduler;
         LTPFramework;
      }

      Session -> SuiteScheduler;
      TestScheduler -> GenericSUT;
      GenericSUT -> ComChannel;

      Session -> LTPFramework;
      TestScheduler -> LTPFramework;
   }

|
|

Plugins system
--------------

.. inheritance-diagram::
   libkirk.com.ComChannel
   libkirk.plugin.Plugin
   libkirk.sut.SUT
   libkirk.sut_base.GenericSUT
   libkirk.channels.shell.ShellComChannel
   libkirk.channels.ltx_chan.LTXComChannel
   libkirk.channels.qemu.QemuComChannel
   libkirk.channels.ssh.SSHComChannel
   :include-subclasses:
   :parts: 1

|
|

Exceptions
----------

.. inheritance-diagram::
   libkirk.errors
   :parts: 1

|
|
