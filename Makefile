# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2023 SUSE LLC <andrea.cervesato@suse.com>
#
# Install script for Linux Testing Project

top_srcdir		?= ../..

include $(top_srcdir)/include/mk/env_pre.mk

BASE_DIR		:= $(abspath $(DESTDIR)/$(prefix))

install:
	mkdir -p $(BASE_DIR)/libkirk

	install -m 00644 $(top_srcdir)/tools/kirk/libkirk/*.py $(BASE_DIR)/libkirk
	install -m 00775 $(top_srcdir)/tools/kirk/kirk $(BASE_DIR)/kirk

	ln -s $(BASE_DIR)/runltp-ng $(BASE_DIR)/kirk

include $(top_srcdir)/include/mk/generic_leaf_target.mk
