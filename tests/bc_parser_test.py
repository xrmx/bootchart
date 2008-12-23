import sys, os, re, struct
from collections import defaultdict
import unittest
import bc_parser


class TestBCParser(unittest.TestCase):
    
    def setUp(self):
        self.name = "My first unittest"

    def testParseProcPsLog(self):    
	#parseProcPsLog(fileName, forkMap)
	pass
        

    def testparseProcStatLog(self):
	samples = parseProcStatLog()
	self.assertEqual(408, len(samples))
	
	#self.assert_(element in self.seq)

if __name__ == '__main__':
    unittest.main()

