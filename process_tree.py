import sys, os, re, struct
from collections import defaultdict


class ProcessTree:

	def __init__(self, psstats, monitoredApp, prune):
	
		self.psstats = psstats
		
		self.processList = psstats.processList
		self.samplePeriod = psstats.samplePeriod
		
		self.build()
		
	
	
	def build(self):
		
		self.processTree = []
		for proc in processList:
			if not proc.parent:
				processTree.append(proc)
			else:
				proc.parent.childList.append(proc)
				
				
	def getStartTime(self, processSubtree):
		if not processSubtree:
			return 100000000;
		return min( [min(proc.starttime, self.getStartTime(proc.childList)) for proc in processSubtree] )
	
	def getEndTime(self, processSubtree):
		if not processSubtree:
			return -100000000;
		return max( [max(proc.starttime + proc.duration, self.getEndTime(proc.childList)) for proc in processSubtree] )
		
	
	def getMaxPid(self, processSubtree):
		if not processSubtree:
			return -100000000;
		return max( [max(proc.pid, self.getMaxPid(proc.childList)) for proc in processSubtree] )

