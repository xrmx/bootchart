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
		
		
	def prune(self, processSubtree, parent) {
		int numRemoved = 0;

		for proc in processSubtree:
			if parent || len(proc.childList) == 0:
				""""
				 * Filter out sleepy background processes, short-lived
				 * processes and bootchart's anaylsis tools.
				"""
				processEnd = proc.getEndTime()
				
				prune = (not p.active) and 
					processEnd.getTime() >= startTime.getTime() + duration &&
					p.startTime.getTime() > startTime.getTime() &&
					p.duration > 0.9 * duration &&
					numNodes(p.childList) == 0) {
					// idle background processes without children
					prune = true;
				} else if (p.duration <= 2 * samplePeriod) {
					// short-lived process
					prune = true;
				}
				
				if (prune) { 
					i.remove();
					numRemoved++;
					for (Iterator j=p.childList.iterator(); j.hasNext(); ) {
						i.add(j.next());
						i.previous();
					}
				} else {
					numRemoved += prune(p.childList, p);
				}
			} else {
				numRemoved += prune(p.childList, p);
			}
		}
		return numRemoved;
	}
	
