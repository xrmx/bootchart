#
# ***********************************************************************
#  Warning: This file is auto-generated from main.py.in - edit it there.
# ***********************************************************************
#
#  pybootchartgui is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  pybootchartgui is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with pybootchartgui. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import sys
import os
import optparse

from . import parsing
from . import batch


PY2 = sys.version_info[0] == 2

def _mk_options_parser():
	"""Make an options parser."""
	usage = "%prog [options] PATH, ..., PATH"
	version = "%prog v@VER@"
	parser = optparse.OptionParser(usage, version=version)
	if PY2:
		parser.add_option("-i", "--interactive", action="store_true", dest="interactive", default=False,
				  help="start in active mode")
	parser.add_option("-f", "--format", dest="format", default="png", choices=["png", "svg", "pdf"],
			  help="image format (png, svg, pdf); default format png")
	parser.add_option("-o", "--output", dest="output", metavar="PATH", default=None,
			  help="output path (file or directory) where charts are stored")
	parser.add_option("-n", "--no-prune", action="store_false", dest="prune", default=True,
			  help="do not prune the process tree")
	parser.add_option("-q", "--quiet", action="store_true", dest="quiet", default=False,
			  help="suppress informational messages")
	parser.add_option("-t", "--boot-time", action="store_true", dest="boottime", default=False,
			  help="only display the boot time of the boot in text format (stdout)")	
	parser.add_option("--very-quiet", action="store_true", dest="veryquiet", default=False,
			  help="suppress all messages except errors")
	parser.add_option("--verbose", action="store_true", dest="verbose", default=False,
			  help="print all messages")
	parser.add_option("--profile", action="store_true", dest="profile", default=False,
			  help="profile rendering of chart (only useful when in batch mode indicated by -f)")
	parser.add_option("--show-pid", action="store_true", dest="show_pid", default=False,
			  help="show process ids in the bootchart as 'processname [pid]'")
	parser.add_option("--show-all", action="store_true", dest="show_all", default=False,
			  help="show all process information in the bootchart as '/process/path/exe [pid] [args]'")
	parser.add_option("--crop-after", dest="crop_after", metavar="PROCESS", default=None,
			  help="crop chart when idle after PROCESS is started")
	parser.add_option("--annotate", action="append", dest="annotate", metavar="PROCESS", default=None,
			  help="annotate position where PROCESS is started; can be specified multiple times. " +
			       "To create a single annotation when any one of a set of processes is started, use commas to separate the names")
	parser.add_option("--annotate-file", dest="annotate_file", metavar="FILENAME", default=None,
			  help="filename to write annotation points to")
	return parser

class Writer:
	def __init__(self, write, options):
		self.write = write
		self.options = options
		
	def error(self, msg):
		self.write(msg)

	def warn(self, msg):
		if not self.options.quiet:
			self.write(msg)

	def info(self, msg):
		if self.options.verbose:
			self.write(msg)

	def status(self, msg):
		if not self.options.quiet:
			self.write(msg)

def _mk_writer(options):
	def write(s):
		print(s)
	return Writer(write, options)
	
def _get_filename(paths, options):
	"""Construct a usable filename for outputs based on the paths and options given on the commandline."""
	dname = ""
	fname = "bootchart"

	if not options.output:
		options.output = '.'.join([fname, options.format])

	if not os.path.isdir(options.output):
		return options.output

	dname = options.output
	if len (paths) == 1:
		path = paths[0]
		if os.path.isdir(path):
			fname = os.path.split(path)[-1]
		elif os.path.splitext(path)[1] in [".tar", ".tgz", ".tar.gz"]:
			fname = os.path.splitext(path)[0]
			# strip directory
			fname = os.path.split(fname)[-1]
	return os.path.join (dname, fname + "." + options.format)

def main(argv=None):
	try:
		if argv is None:
			argv = sys.argv[1:]
	
		parser = _mk_options_parser()
		options, args = parser.parse_args(argv)
		writer = _mk_writer(options)

		if len(args) == 0:
			print("No path given, trying /var/log/bootchart.tgz")
			args = [ "/var/log/bootchart.tgz" ]

		trace = parsing.Trace(writer, args, options)

		if getattr(options, 'interactive', False):
			from . import gui
			gui.show(trace, options)
		elif options.boottime:
			import math
			proc_tree = trace.proc_tree
			if proc_tree.idle:
			    duration = proc_tree.idle
			else:
			    duration = proc_tree.duration
			dur = duration / 100.0
			print('%02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60)))
		else:
			if options.annotate_file:
				with open (options.annotate_file, "w") as f:
					for time in trace.times:
						if time is not None:
							# output as ms
							print(time * 10, file=f)
						else:
							print(file=f)
			filename = _get_filename(args, options)
			def render():
				batch.render(writer, trace, options, filename)
			if options.profile:
				import cProfile
				import pstats
				profile = '%s.prof' % os.path.splitext(filename)[0]
				cProfile.runctx('render()', globals(), locals(), profile)
				p = pstats.Stats(profile)
				p.strip_dirs().sort_stats('time').print_stats(20)
			else:
				render()

		return 0
	except parsing.ParseError as ex:
		print(("Parse error: %s" % ex))
		return 2


if __name__ == '__main__':
	sys.exit(main())
