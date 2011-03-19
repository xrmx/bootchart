import sys, os, re, struct, operator, math
from collections import defaultdict
import unittest

sys.path.insert(0, os.getcwd())

import pybootchartgui.parsing as parsing
import pybootchartgui.main as main

debug = False

def floatEq(f1, f2):
	return math.fabs(f1-f2) < 0.00001

bootchart_dir = os.path.join(os.path.dirname(sys.argv[0]), '../../examples/1/')
parser = main._mk_options_parser()
options, args = parser.parse_args(['--q', bootchart_dir])
writer = main._mk_writer(options)

class TestBCParser(unittest.TestCase):
    
	def setUp(self):
		self.name = "My first unittest"
		self.rootdir = bootchart_dir

	def mk_fname(self,f):
		return os.path.join(self.rootdir, f)

	def testParseHeader(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('header'))
		self.assertEqual(6, len(state.headers))
		self.assertEqual(2, parsing.get_num_cpus(state.headers))

	def test_parseTimedBlocks(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('proc_diskstats.log'))
		self.assertEqual(141, len(state.disk_stats))		

	def testParseProcPsLog(self):
		trace = parsing.Trace(writer, args, options)
		state = parsing.parse_file(writer, trace, self.mk_fname('proc_ps.log'))
		samples = state.ps_stats
		processes = samples.process_list
		sorted_processes = sorted(processes, key=lambda p: p.pid )
		
		for index, line in enumerate(open(self.mk_fname('extract2.proc_ps.log'))):
			tokens = line.split();
			process = sorted_processes[index]
			if debug:	
				print(tokens[0:4])
				print(process.pid, process.cmd, process.ppid, len(process.samples))
				print('-------------------')
			
			self.assertEqual(tokens[0], str(process.pid))
			self.assertEqual(tokens[1], str(process.cmd))
			self.assertEqual(tokens[2], str(process.ppid))
			self.assertEqual(tokens[3], str(len(process.samples)))
        

	def testparseProcDiskStatLog(self):
		trace = parsing.Trace(writer, args, options)
		state_with_headers = parsing.parse_file(writer, trace, self.mk_fname('header'))
		state_with_headers.headers['system.cpu'] = 'xxx (2)'
		samples = parsing.parse_file(writer, state_with_headers, self.mk_fname('proc_diskstats.log')).disk_stats
		self.assertEqual(141, len(samples))
	
		for index, line in enumerate(open(self.mk_fname('extract.proc_diskstats.log'))):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:		
				print(line.rstrip())
				print(sample)
				print('-------------------')
			
			self.assertEqual(tokens[0], str(sample.time))
			self.assert_(floatEq(float(tokens[1]), sample.read))
			self.assert_(floatEq(float(tokens[2]), sample.write))
			self.assert_(floatEq(float(tokens[3]), sample.util))
	
	def testparseProcStatLog(self):
		trace = parsing.Trace(writer, args, options)
		samples = parsing.parse_file(writer, trace, self.mk_fname('proc_stat.log')).cpu_stats
		self.assertEqual(141, len(samples))
			
		for index, line in enumerate(open(self.mk_fname('extract.proc_stat.log'))):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:
				print(line.rstrip())
				print(sample)
				print('-------------------')
			self.assert_(floatEq(float(tokens[0]), sample.time))
			self.assert_(floatEq(float(tokens[1]), sample.user))
			self.assert_(floatEq(float(tokens[2]), sample.sys))
			self.assert_(floatEq(float(tokens[3]), sample.io))
	
	def testParseLogDir(self):		
		res = parsing.parse(writer, [self.rootdir], False, None, None)
		self.assertEqual(6, len(res))
	
if __name__ == '__main__':
    unittest.main()

