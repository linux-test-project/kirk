.. SPDX-License-Identifier: GPL-2.0-or-later

Implementing a new Framework
============================

Every testing framework has its own setup, defining tests folders, data, and
variables. For this reason, the `Framework` class provides a generic API that,
once implemented, allows you to define a specific testing framework. 

The class implementation must be included inside the `libkirk` folder and will
be used as an abstraction layer between the `kirk` scheduler and the specific
testing framewiork.
