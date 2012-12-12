import sys

_writer = None

class Writer:
	def __init__(self, options):
		self.options = options

	def _write(self, s):
		sys.stderr.write(s + "\n")

def init(options):
	global _writer
	_writer = Writer(options)

def fatal(msg):
	_writer._write(msg)
	exit(1)

def error(msg):
	_writer._write(msg)

def warn(msg):
	if not _writer.options.quiet:
		_writer._write(msg)

def info(msg):
	if _writer.options.verbose > 0:
		_writer._write(msg)

def debug(msg):
	if _writer.options.verbose > 1:
		_writer._write(msg)

def status(msg):
	if not _writer.options.quiet:
		_writer._write(msg)

