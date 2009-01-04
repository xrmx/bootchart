import sys, os, re, struct
from collections import defaultdict

LOGGER_PROC = 'bootchartd'
EXPLODER_PROCESSES = set(['hwup'])

class ProcessTree:

	def __init__(self, psstats, monitoredApp, prune):
		self.process_tree = []
		self.psstats = psstats		
		self.process_list = psstats.process_list
		self.sample_period = psstats.sample_period
		
		self.start_time = psstats.start_time
		self.end_time = psstats.end_time
		self.duration = self.end_time - self.start_time

		self.build()
		removed = self.merge_logger(self.process_tree, LOGGER_PROC, monitoredApp, False)
		print "Merged %i logger processes" % removed

		if prune:
			removed = self.prune(self.process_tree, None)
			print "Pruned %i processes" % removed
			removed = self.merge_exploders(self.process_tree, EXPLODER_PROCESSES)
			print "Pruned %i exploders" % removed
			removed = self.merge_siblings(self.process_tree)
			print "Pruned %i threads" % removed
			removed = self.merge_runs(self.process_tree)
			print "Pruned %i runs" % removed

		self.num_proc = self.num_nodes(self.process_list)
	
	def build(self):		
		self.process_tree = []
		for proc in self.process_list:
			if not proc.parent:
				self.process_tree.append(proc)
			else:
				proc.parent.child_list.append(proc)
	
	def num_nodes(self, process_list):
		nodes = 0
		for proc in process_list:
			nodes = nodes + 1 + self.num_nodes(proc.child_list)
		return nodes
				
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

	def prune(self, process_subtree, parent):
		num_removed = 0
		work = process_subtree
		for p in list(process_subtree):
			if parent != None or len(p.child_list) == 0:
				# Filter out sleepy background processes,
				# short-lived processes and bootcharts'
				# analysis tools.
				process_end = p.startTime + p.duration
				prune = False
				if not p.active and \
				   process_end >= self.start_time + self.duration and \
                                   p.startTime > self.start_time and \
                                   p.duration > 0.9 * self.duration and \
                                   self.num_nodes(p.child_list) == 0:
					# idle background process without children
					prune = True
				elif p.duration <= 2 * self.sample_period:
					# short-lived process
					prune = True

				if prune:
					process_subtree.remove(p)
					num_removed += 1
					# add all children?
				else:
					num_removed += self.prune(p.child_list, p)
			else:
				num_removed += self.prune(p.child_list, p)

		return num_removed

	def merge_logger(self, process_subtree, logger_proc, monitored_app, app_tree):
		num_removed = 0
		for p in process_subtree:
			is_app_tree = app_tree
			if logger_proc == p.cmd and not app_tree:
				is_app_tree = True
				num_removed += self.merge_logger(p.child_list, logger_proc, monitored_app, is_app_tree)
				# don't remove the logger itself
				continue

			if app_tree and monitored_app != None and monitored_app == p.cmd:
				is_app_tree = False

			if is_app_tree:
				for child in p.child_list:
					self.__merge_processes(p, child)
					num_removed += 1
				p.child_list = []
			else:
				num_removed += self.merge_logger(p.child_list, logger_proc, monitored_app, is_app_tree)
		return num_removed

	def merge_exploders(self, process_subtree, processes):
		num_removed = 0
		for p in process_subtree:
			if processes in processes and len(p.child_list) > 0:
				subtreemap = self.getProcessMap(p.child_list)
				for child in subtreemap.values():
					self.__merge_processes(p, child)
				num_removed += len(subtreemap)
				p.child_list = []
				p.cmd += " (+)"
			else:
				num_removed += self.merge_exploders(p.child_list, processes)
		return num_removed

	def merge_siblings(self,process_subtree):
		num_removed = 0
		idx = 0
		while idx < len(process_subtree)-1:
			p = process_subtree[idx]
			nextp = process_subtree[idx+1]
			if nextp.cmd == p.cmd:
				process_subtree.pop(idx+1)
				idx -= 1
				num_removed += 1
				for child in nextp.child_list:
					p.child_list.append(child)
				self.__merge_processes(p, nextp)
			num_removed += self.merge_siblings(p.child_list)
			idx += 1
		if len(process_subtree) > 0:
			p = process_subtree[-1]
			num_removed += self.merge_siblings(p.child_list)
		return num_removed

	def merge_runs(self, process_subtree):
		num_removed = 0
		idx = 0
		while idx < len(process_subtree):
			p = process_subtree[idx]
			if len(p.child_list) == 1 and p.child_list[0].cmd == p.cmd:
				child = p.child_list[0]
				p.child_list = list(child.child_list)
				p.samples.extend(child.samples)
				ptime = p.startTime
				nptime = child.startTime
				p.startTime = min(ptime, nptime)
				pendtime = max(ptime + p.duration, nptime + child.duration)
				p.duration = pendtime - p.startTime
				num_removed += 1
				continue
			num_removed += self.merge_runs(p.child_list)
			idx += 1
		return num_removed

	def __merge_processes(self, p1, p2):
		p1.samples.extend(p2.samples)
		p1time = p1.startTime
		p2time = p2.startTime
		p1.startTime = min(p1time, p2time)
		pendtime = max(p1time + p1.duration, p2time + p2.duration)
		p1.duration = pendtime - p1.startTime
