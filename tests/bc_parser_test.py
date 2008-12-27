import sys, os, re, struct
from collections import defaultdict
import unittest

print sys.path.insert(0, os.getcwd())

import bc_parser


class TestBCParser(unittest.TestCase):
    
    def setUp(self):
        self.name = "My first unittest"

    def testParseProcPsLog(self):    
	#parseProcPsLog(fileName, forkMap)
	pass
        

    def testparseProcStatLog(self):
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
		if not line.rstrip() == str(sample):
			break
	
	sample200 = samples[200]
	self.assertEqual(1620.0, sample200.read)
	self.assertEqual(0.0, sample200.write)
	self.assertEqual(2216, sample200.time)
	
	#self.assert_(element in self.seq)

if __name__ == '__main__':
    unittest.main()

