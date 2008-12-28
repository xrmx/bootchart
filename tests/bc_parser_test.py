import sys, os, re, struct, operator
from collections import defaultdict
import unittest

print sys.path.insert(0, os.getcwd())

import bc_parser


class TestBCParser(unittest.TestCase):
    
	def setUp(self):
		self.name = "My first unittest"

	def testParseProcPsLog(self):    
		samples = bc_parser.parseProcPsLog('examples/1/proc_ps.log', {})

		print samples[2]
		print samples[3]	
		print len(samples[0])
	
		processes = samples[0]
		sorted_processes = sorted(processes, key=lambda p: p.pid )
		
		for index, line in enumerate(open('examples/1/extract2.proc_ps.log')):
			tokens = line.split();
			process = sorted_processes[index]
			print tokens[0:4]
			print process.pid, process.cmd, process.ppid, len(process.samples)
			print '-------------------'
			#if process.pid != process.ppid: break
			self.assertEqual(tokens[0], str(process.pid))
			self.assertEqual(tokens[1], str(process.cmd))
			self.assertEqual(tokens[2], str(process.ppid))
			self.assertEqual(tokens[3], str(len(process.samples)))
        

	def testparseProcDiskStatLog(self):
		if self:
			return
		samples = bc_parser.parseProcDiskStatLog(2, 'examples/1/proc_diskstats.log')
		self.assertEqual(282, len(samples))
	
		sample1 = samples[0]
		self.assertEqual(0.0, sample1.read)
		self.assertEqual(0.0, sample1.write)
		self.assertEqual(176, sample1.time)
	
		for index, line in enumerate(open('examples/1/extract.proc_diskstats.log')):
			tokens = line.split('\t')
			sample = samples[index]
			print line.rstrip()
			print sample
			print '-------------------'
			self.assertEqual(line.rstrip(), str(sample))
		
		sample200 = samples[200]
		self.assertEqual(1620.0, sample200.read)
		self.assertEqual(0.0, sample200.write)
		self.assertEqual(2216, sample200.time)
	
		#self.assert_(element in self.seq)

	
	def testparseProcStatLog(self):
		pass

if __name__ == '__main__':
    unittest.main()

