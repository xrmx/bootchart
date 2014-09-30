VER=0.14.7
PKG_NAME=bootchart2
PKG_TARBALL=$(PKG_NAME)-$(VER).tar.bz2

CROSS_COMPILE ?= $(CONFIG_CROSS_COMPILE:"%"=%)

CC ?= $(CROSS_COMPILE)gcc
CFLAGS ?= -g -Wall -O0
CPPFLAGS ?=

# Normally empty, but you can use program_prefix=mmeeks- or program_suffix=2
# to install bootchart2 on a system that already has other projects that also
# call themselves bootchart.
PROGRAM_PREFIX ?=
PROGRAM_SUFFIX ?=

# Prefix for things that must reside on the root filesystem.
# "" for e.g. Debian; /usr for distributions with /usr unification.
EARLY_PREFIX ?=

BINDIR ?= /usr/bin
PYTHON ?= python
DOCDIR ?= /usr/share/docs/$(PROGRAM_PREFIX)bootchart$(PROGRAM_SUFFIX)
MANDIR ?= /usr/share/man/man1
# never contains /usr; typically /lib, /lib64 or e.g. /lib/x86_64-linux-gnu
LIBDIR ?= /lib
PKGLIBDIR ?= $(EARLY_PREFIX)$(LIBDIR)/$(PROGRAM_PREFIX)bootchart$(PROGRAM_SUFFIX)

ifndef PY_LIBDIR
ifndef NO_PYTHON_COMPILE
PY_LIBDIR := $(shell $(PYTHON) -c "from distutils import sysconfig; print(sysconfig.get_config_var('DESTLIB'))")
else
PY_LIBDIR = /usr$(LIBDIR)/python2.6
endif
endif
PY_SITEDIR ?= $(PY_LIBDIR)/site-packages
LIBC_A_PATH = /usr$(LIBDIR)
# Always lib, even on systems that otherwise use lib64
SYSTEMD_UNIT_DIR = $(EARLY_PREFIX)/lib/systemd/system
COLLECTOR = \
	collector/collector.o \
	collector/output.o \
	collector/tasks.o \
	collector/tasks-netlink.o \
	collector/dump.o

all: \
	bootchart-collector \
	bootchartd \
	bootchart2.service \
	bootchart2-done.service \
	bootchart2-done.timer \
	pybootchartgui/main.py

%.o:%.c
	$(CC) $(CFLAGS) $(LDFLAGS) -pthread \
		-DEARLY_PREFIX='"$(EARLY_PREFIX)"' \
		-DLIBDIR='"$(LIBDIR)"' \
		-DPKGLIBDIR='"$(PKGLIBDIR)"' \
		-DPROGRAM_PREFIX='"$(PROGRAM_PREFIX)"' \
		-DPROGRAM_SUFFIX='"$(PROGRAM_SUFFIX)"' \
		-DVERSION='"$(VER)"' \
		$(CPPFLAGS) \
		-c $^ -o $@

substitute_variables = \
	sed -s \
		-e "s:@LIBDIR@:$(LIBDIR):g" \
		-e "s:@PKGLIBDIR@:$(PKGLIBDIR):" \
		-e "s:@PROGRAM_PREFIX@:$(PROGRAM_PREFIX):" \
		-e "s:@PROGRAM_SUFFIX@:$(PROGRAM_SUFFIX):" \
		-e "s:@EARLY_PREFIX@:$(EARLY_PREFIX):" \
		-e "s:@VER@:$(VER):"

bootchartd: bootchartd.in
	$(substitute_variables) $^ > $@

%.service: %.service.in
	$(substitute_variables) $^ > $@

%.timer: %.timer.in
	$(substitute_variables) $^ > $@

bootchart-collector: $(COLLECTOR)
	$(CC) $(CFLAGS) $(LDFLAGS) -pthread -Icollector -o $@ $^

pybootchartgui/main.py: pybootchartgui/main.py.in
	$(substitute_variables) $^ > $@

py-install-compile: pybootchartgui/main.py
	install -d $(DESTDIR)$(PY_SITEDIR)/pybootchartgui
	cp pybootchartgui/*.py $(DESTDIR)$(PY_SITEDIR)/pybootchartgui
	install -D -m 755 pybootchartgui.py $(DESTDIR)$(BINDIR)/pybootchartgui
	[ -z "$(NO_PYTHON_COMPILE)" ] && ( cd $(DESTDIR)$(PY_SITEDIR)/pybootchartgui ; \
		$(PYTHON) $(PY_LIBDIR)/py_compile.py *.py ; \
		PYTHONOPTIMIZE=1 $(PYTHON) $(PY_LIBDIR)/py_compile.py *.py ); :

install-chroot:
	install -d $(DESTDIR)$(PKGLIBDIR)/tmpfs

install-collector: all install-chroot
	install -m 755 -D bootchartd $(DESTDIR)$(EARLY_PREFIX)/sbin/$(PROGRAM_PREFIX)bootchartd$(PROGRAM_SUFFIX)
	install -m 644 -D bootchartd.conf $(DESTDIR)/etc/$(PROGRAM_PREFIX)bootchartd$(PROGRAM_SUFFIX).conf
	install -m 755 -D bootchart-collector $(DESTDIR)$(PKGLIBDIR)/$(PROGRAM_PREFIX)bootchart$(PROGRAM_SUFFIX)-collector

install-docs:
	install -m 644 -D README $(DESTDIR)$(DOCDIR)/README
	install -m 644 -D README.pybootchart $(DESTDIR)$(DOCDIR)/README.pybootchart
	mkdir -p $(DESTDIR)$(MANDIR)
	gzip -c bootchart2.1 > $(DESTDIR)$(MANDIR)/bootchart2.1.gz
	gzip -c bootchartd.1 > $(DESTDIR)$(MANDIR)/$(PROGRAM_PREFIX)bootchartd$(PROGRAM_SUFFIX).1.gz
	gzip -c pybootchartgui.1 > $(DESTDIR)$(MANDIR)/pybootchartgui.1.gz

install-service:
	mkdir -p $(DESTDIR)$(SYSTEMD_UNIT_DIR)
	install -m 0644 bootchart2.service \
	       bootchart2-done.service \
	       bootchart2-done.timer \
	       $(DESTDIR)$(SYSTEMD_UNIT_DIR)

install: all py-install-compile install-collector install-service install-docs

clean:
	-rm -f bootchart-collector bootchart-collector-dynamic \
	collector/*.o pybootchartgui/main.py bootchartd \
	bootchart2-done.service bootchart2-done.timer bootchart2.service

dist:
	COMMIT_HASH=`git show-ref -s -h | head -n 1` ; \
	git archive --prefix=$(PKG_NAME)-$(VER)/ --format=tar $$COMMIT_HASH \
		| bzip2 -f > $(PKG_TARBALL)

test: pybootchartgui/tests
	for f in pybootchartgui/tests/*.py;\
	do \
		echo "Testing $$f...";\
		$(PYTHON) "$$f";\
	done
