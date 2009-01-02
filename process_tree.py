import sys, os, re, struct
from collections import defaultdict


class ProcessTree:

	def __init__(self, psstats, monitoredApp, prune):
		self.processTree = []
		self.psstats = psstats		
		self.process_list = psstats.process_list
		self.sample_period = psstats.sample_period
		
		self.start_time = psstats.start_time
		self.end_time = psstats.end_time
		self.duration = self.end_time - self.start_time

		self.build()
	
	def build(self):		
		self.processTree = []
		for proc in self.process_list:
			if not proc.parent:
				self.processTree.append(proc)
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

