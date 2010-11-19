			    bootchart2
			   ------------

	bootchart2 was created from the fusion of three separate
pieces of work. First - the original bootchart: a shell script, and a
Java visualisation tool written by Ziga Mahkovec. Some of the original
shell scripting, and the concept remain unchanged from this time.

	bootchart2 replaces the Java visualisation with the more
friendly and flexible pybootchartgui (cf. README.pybootchart) written
by Anders Norgaard and Henning Niss, this lives mostly in the
pybootchart/ sub-directory.

	bootchart2 embeds a new collector, based on a port to C of the
inner-loop of the original bootchart collector shell-script by Scott
James Remnant. This has been subsequently re-written by Michael Meeks
to use the higher granularity 'taskstat' data available via a twisted
netlink interface, amongst other new features.


			    Using bootchart2 ?
			   --------------------

	After install, simply add these options to your kernel
command-line, normally in /boot/grub/menu.lst:

	initcall_debug printk.time=y quiet init=/sbin/bootchartd ...

	Then - after bootup, run 'pybootchartgui -i' to get an interactive
chart rendering tool. If you want to chart the initrd, add
rdinitrd=/sbin/bootchartd to the kernel command-line.

	To make bootchart2 work best, please ensure your kernel is
configured with CONFIG_PROC_EVENTS=y and CONFIG_TASKSTATS=y, without
these we are slower, less accurate, and produce an uglier task 
hierarchy.

	If you want to start bootchart2 in a dracut (version >= 008)
initramfs, you have to change "init=/sbin/bootchartd" to 
"rdinit=/sbin/bootchartd" and regenerate the initramfs with bootchart support
with "# dracut -f -a bootchart".

			    Why bootchart2 ?
			   ------------------

	There are a number of interesting additional features:

	* higher resolution - the taskstat interface gives nanosecond
	  timing information, where /proc/*/stat information is far,
	  far less reliable and useful.

	* higher performance - the C re-write allows us to collect more
	  data, more quickly - sampling at ~50+Hz.

	* using PROC_EVENTS we can determine accurate process parentage
	  without needing to use a (poorly maintained) 'acct' binary

	* no Java dependency - with the visualisation in easy-to-hack
	  python, development is quicker, and dependencies more commonly
	  found.

	* simpler wrappers - by using ptrace to connect to and extract
	  data from the collector, we no longer require a consistently
	  visible set of logs accessible via a shared file-system.

	* built-in visualisation - allowing some level of interaction,
	  zoom and so on.

	* better rendering - render to png, or svg, with added event
	  annotation support, and 'show more' functionality.

	* cumulative, and total CPU time graphing in the boot-chart.

	* and no doubt more by the time this is actually read.


			    Contributing
			   --------------

	For potential future work, see the TODO, and/or mail the authors,
wander over to #bootchart2 on irc.freenode.net. All patches most welcome.
