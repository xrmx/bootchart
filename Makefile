CC = gcc
CFLAGS = -g -Wall -Os

BINDIR ?= /usr/bin
PY_LIBDIR ?= /usr/lib/python2.6
PY_SITEDIR ?= $(PY_LIBDIR)/site-packages

all: bootchart-collector

bootchart-collector: collector/bootchart-collector.o
	$(CC) -o $@ $<

py-install-compile:
	install -d $(DESTDIR)$(PY_SITEDIR)/pybootchartgui
	cp pybootchartgui/*.py $(DESTDIR)$(PY_SITEDIR)/pybootchartgui
	install -D -m 755 pybootchartgui.py $(DESTDIR)$(BINDIR)/pybootchartgui
	cd $(DESTDIR)$(PY_SITEDIR)/pybootchartgui ; \
		python $(PY_LIBDIR)/py_compile.py *.py ; \
		PYTHONOPTIMIZE=1 python $(PY_LIBDIR)/py_compile.py *.py

install: all py-install-compile
	install -m 755 -D bootchartd $(DESTDIR)/sbin/bootchartd
	install -m 644 -D bootchartd.conf $(DESTDIR)/etc/bootchartd.conf
	install -m 755 -D bootchart-collector $(DESTDIR)/lib/bootchart/bootchart-collector

clean:
	-rm -f bootchart-collector collector/*.o

#dist:
#	bzr export bootchart-collector-0.90.4.1.tar.bz2
