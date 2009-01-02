import sys, os, re, struct, operator, math
from collections import defaultdict
import unittest

print sys.path.insert(0, os.getcwd())

import bc_parser

debug = False

def floatEq(f1, f2):
	return math.fabs(f1-f2) < 0.00001

class TestBCParser(unittest.TestCase):
    
	def setUp(self):
		self.name = "My first unittest"
		
	def testParseHeader(self):
		headers = bc_parser.parseHeaders('examples/1/header')
		self.assertEqual(7, len(headers))
		print headers

	def testParseProcPsLog(self):
		samples = bc_parser.parseProcPsLog('examples/1/proc_ps.log', {})

		processes = samples[0]
		sorted_processes = sorted(processes, key=lambda p: p.pid )
		
		for index, line in enumerate(open('examples/1/extract2.proc_ps.log')):
			tokens = line.split();
			process = sorted_processes[index]
			if debug:	
				print tokens[0:4]
				print process.pid, process.cmd, process.ppid, len(process.samples)
				print '-------------------'
			
			self.assertEqual(tokens[0], str(process.pid))
			self.assertEqual(tokens[1], str(process.cmd))
			self.assertEqual(tokens[2], str(process.ppid))
			self.assertEqual(tokens[3], str(len(process.samples)))
        

	def testparseProcDiskStatLog(self):
		samples = bc_parser.parseProcDiskStatLog(2, 'examples/1/proc_diskstats.log')
		self.assertEqual(141, len(samples))
	
		for index, line in enumerate(open('examples/1/extract.proc_diskstats.log')):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:		
				print line.rstrip(), 
				print sample
				print '-------------------'
			
			self.assertEqual(tokens[0], str(sample.time))
			self.assert_(floatEq(float(tokens[1]), sample.read))
			self.assert_(floatEq(float(tokens[2]), sample.write))
			self.assert_(floatEq(float(tokens[3]), sample.util))
	
	def testparseProcStatLog(self):
		samples = bc_parser.parseProcStatLog('examples/1/proc_stat.log')
		self.assertEqual(141, len(samples))
			
		for index, line in enumerate(open('examples/1/extract.proc_stat.log')):
			tokens = line.split('\t')
			sample = samples[index]
			if debug:
				print line.rstrip()
				print sample
				print '-------------------'
			self.assert_(floatEq(float(tokens[0]), sample.time))
			self.assert_(floatEq(float(tokens[1]), sample.user))
			self.assert_(floatEq(float(tokens[2]), sample.sys))
			self.assert_(floatEq(float(tokens[3]), sample.io))
	
if __name__ == '__main__':
    unittest.main()

