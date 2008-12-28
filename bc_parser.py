import sys, os, re, struct
from collections import defaultdict


class DiskStatSample:
	def __init__(self):
		self.values = [0,0,0]
		self.changes = [0,0,0]
	def __str__(self):
		return 'Values ' +  str(self.values) + ", Changes " + str(self.changes);

class CPUSample:
	def __init__(self, time, user, sys, io):
		self.time = time
		self.user = user
		self.sys = sys
		self.io = io

	def __str__(self):
		return self.time + "\t" + str(self.user) + "\t" + str(self.sys) + "\t" + str(self.io);
		
class ProcessSample:
	def __init__(self, time, state, cpuSample, diskUtil, diskTPut):
		self.time = time
		self.state = state
		self.cpuSample = cpuSample
		self.diskUtil = diskUtil
		self.diskTPut = diskTPut
		
	def __str__(self):
		return str(self.time) + "\t" + str(self.state) + "\t" + str(self.cpuSample) + "\t" + self.diskUtil + "\t" + self.diskTPut;

class Process:
	
	def __init__(self, pid, cmd, ppid, startTime):

		self.pid = pid
		self.cmd = cmd.strip('(').strip(')')
		self.ppid = ppid
		self.startTime = startTime
		self.samples = []
		
		self.duration = 0
		self.active = None
		
		self.lastUserCpuTime = None
		self.lastSysCpuTime = None
	
	def __str__(self):
		return " ".join([str(self.pid), self.cmd, self.ppid, '[' + ','.join([str(sample) for sample in self.samples]) + ']' ])
	
	def calcStats(self, samplePeriod):
		if self.samples:
			firstSample = self.samples[0]
			lastSample = self.samples[-1]
			self.startTime = min(firstSample.time, self.startTime)
			self.duration = lastSample.time - self.startTime + samplePeriod
			
		activeCount = sum( [1 for sample in self.samples if sample.cpuSample and sample.cpuSample.sys + sample.cpuSample.user + sample.cpuSample.io > 0.0] )
		activeCount = activeCount + sum( [1 for sample in self.samples if sample.state == 'D'] )
		self.active = (activeCount>2)
		
	def calcLoad(self, userCpu, sysCpu, interval):
		
		userCpuLoad = (userCpu - self.lastUserCpuTime) / interval
		sysCpuLoad = (sysCpu - self.lastSysCpuTime) / interval
		cpuLoad = userCpuLoad + sysCpuLoad;
		# normalize
		if cpuLoad > 1.0:
			userCpuLoad = userCpuLoad / cpuLoad;
			sysCpuLoad = sysCpuLoad / cpuLoad;
		return (userCpuLoad, sysCpuLoad)
	
	def getEndTime(self):
		return self.startTime + self.duration

class DiskTPutSample:
	def __init__(self, time, read, write):
		self.time = time
		self.read = read
		self.write = write

	def __str__(self):
		return "\t".join([str(self.time), str(self.read), str(self.write)])

	
class DiskUtilSample:
	"""Disk utilization [0.0, 1.0] """

	def __init__(self, time, util):
		self.time = time
		self.util = util

	def __str__(self):
		return "\t".join([str(self.time), str(self.util)])

	
	
def parsePacct(fileName):
	forkMap = defaultdict(list)
	try:
		ffile = open(fileName, 'rb')
		ffileSize = os.path.getsize(fileName)
		while ffile.tell() < ffileSize:
			buf = ffile.read(16)
			bytes = struct.unpack('B'*len(buf),buf)
			#print 'Version', bytes[1]
		
			pid = struct.unpack('I',ffile.read(4))[0]
			ppid = struct.unpack('I',ffile.read(4))[0]
			
			forkMap[ppid].append(pid)
			
			ffile.read(24) # times, mem, faults, etc.
			
			comm = struct.unpack('c'*16,ffile.read(16))
	
			#print str(comm) + " (" + str(pid) + ") was forked by " + str(ppid) + " " + str(ffile.tell())
	except EOFError:
		print 'Reached end of file'
	
	return forkMap


def getPPIDs(pid, forkMap):
	ppids = [ ppid for (ppid, pids) in forkMap.items() if pid in pids ]
	
	if len(ppids) == 1 and ppid != pid:
		return ppids + getPPIDs(ppids[0], forkMap)
	else:
		return []
			


def parseProcPsLog(fileName, forkMap):
	
	processMap = {}

	blocks = open(fileName).read().split('\n\n')
	numSamples = len(blocks)-1
	#print 'Num blocks', numSamples
	ltime = 0
	startTime = -1
	for block in blocks:
		lines = block.split('\n')

		if not lines[0].isdigit():
			#print lines
			continue
	
		time = int(lines[0])
		
		if startTime == -1: startTime = time
		
		for line in lines[1:]:
			tokens = line.split(' ')
			"""
			 * See proc(5) for details.
			 * 
			 * {pid, comm, state, ppid, pgrp, session, tty_nr, tpgid, flags, minflt, cminflt, majflt, cmajflt, utime, stime,
			 *  cutime, cstime, priority, nice, 0, itrealvalue, starttime, vsize, rss, rlim, startcode, endcode, startstack, 
			 *  kstkesp, kstkeip}
			"""
			
			pid = int(tokens[0])		
			cmd = tokens[1]
			state = tokens[2]
				
			if not cmd.startswith('('):
				#print 'Malformed line', line
				continue
			stime = int(tokens[22])

			if processMap.has_key(pid):
				process = processMap[pid]
				process.cmd = cmd.replace('(', '').replace(')', '') # why rename after latest name??
			else:
				process = Process(pid, tokens[1], tokens[3], min(time, stime))
				processMap[pid] = process
			
			userCpu = int(tokens[13])
			sysCpu = int(tokens[14])
			
			if process.lastUserCpuTime is not None and process.lastSysCpuTime is not None and ltime is not None:
				userCpuLoad, sysCpuLoad = process.calcLoad(userCpu, sysCpu, time - ltime)
				cpuSample = CPUSample('null', userCpu, sysCpu, 0.0)
				process.samples.append(ProcessSample(time, state, cpuSample, 'null', 'null'))
				#print 'Adding sample to process', process
			
			process.lastUserCpuTime = userCpu
			process.lastSysCpuTime = sysCpu
			#print 'Process:', process
		ltime = time	
	
	
	for key in sorted(processMap.keys()):
		#print 'Pid:', key, processMap[key]
		pass
	
	for process in processMap.values():
		ppids = getPPIDs(process.pid, forkMap)
		for ppid in ppids:
			if processMap.has_key(ppid):
				process.ppid = ppid
				process.parent = processMap[process.ppid]
				break
			else:
				print ppid, 'not in processMap???'
	

	samplePeriod = (ltime - startTime)/numSamples	
	
	for process in processMap.values():
		process.calcStats(samplePeriod)
		
	return (processMap.values(), samplePeriod, startTime, ltime)
	
def parseProcStatLog(fileName):
	samples = []
	
	# CPU times {user, nice, system, idle, io_wait, irq, softirq}
	blocks = open(fileName).read().split('\n\n')
	numSamples = len(blocks)-1
	print numSamples, 'blocks ready'
	startTime = -1
	ltimes = None
	for block in blocks:
		lines = block.split('\n')
		#print lines
		if not lines[0].isdigit():
			print lines
			continue	
	
		time = int(lines[0])
		
		
		tokens = lines[1].split(); # {user, nice, system, idle, io_wait, irq, softirq}
		times = [ int(token) for token in tokens[1:] ]
		
		if ltimes:
			user = (times[0] + times[1]) - (ltimes[0] + ltimes[1])
			system = (times[2] + times[5] + times[6]) - (ltimes[2] + ltimes[5] + ltimes[6]);
			idle = times[3] - ltimes[3];
			iowait = times[4] - ltimes[4];
			
			aSum = max(user + system + idle + iowait, 1)
			samples.append( CPUSample(time, user/aSum, system/aSum, iowait/aSum) )
		
		ltimes = times
		
		# skip the rest of statistics lines
		
	print 'Parsed', len(samples), '/proc/stat samples'
	return samples
		
def parseProcDiskStatLog(numCpu, fileName):
	DISK_REGEX = 'hd.|sd.'
	
	diskStatSamples = defaultdict(DiskStatSample)
	diskStats = []
	blocks = open(fileName).read().split('\n\n')
	numSamples = len(blocks)-1
	print numSamples, 'blocks ready ', len(diskStatSamples)
	startTime = -1
	ltime = None
	for block in blocks:
		lines = block.split('\n')
		#print lines
		if not lines[0].isdigit():
			print lines
			continue	
	
		time = int(lines[0])	
	
		# {major minor name rio rmerge rsect ruse wio wmerge wsect wuse running use aveq}
		
		for line in lines:
			tokens = line.split();

			# take only lines with content and only look at the whole disks, eg. sda, not sda1, sda2 etc.
			if len(tokens) != 14 or not re.match(DISK_REGEX, tokens[2]) or not len(tokens[2]) == 3:
				continue
			
			disk = tokens[2]
			
			rsect, wsect, use = int(tokens[5]), int(tokens[9]), int(tokens[12])
			
			sample = diskStatSamples[disk]
						
			if ltime:				
				sample.changes = [rsect-sample.values[0], wsect-sample.values[1], use-sample.values[2]] 

			sample.values = [rsect, wsect, use]

		#print len(diskStatSamples), diskStatSamples
		#if len(diskStatSamples) > 1:
		if ltime:
			interval = time - ltime
			
			sums = [0, 0, 0]
			for sample in diskStatSamples.values():
				for i in range(3):		
					sums[i] = sums[i] + sample.changes[i]
			
			if time == 563:
				print [str(v) for v in diskStatSamples.values()]
				print sums
			
			readTput = sums[0] / 2.0 * 100.0 / interval
			writeTput = sums[1] / 2.0 * 100.0 / interval
			# number of ticks (1000/s), reduced to one CPU, time is in jiffies (100/s)
			util = float( sums[2] ) / 10 / interval / numCpu
			
			#print 'Util', util
			
			diskStats.append(DiskTPutSample(time, readTput, writeTput))
			diskStats.append(DiskUtilSample(time, util))
			
			
		ltime = time
		
	print 'Parsed', len(diskStats)/2, 'samples'
	return diskStats
	
#forkMap = parsePacct(sys.argv[1])
#print getPPIDs(5568, forkMap)
#print parseProcPsLog(sys.argv[2], forkMap)
#parseProcStatLog(sys.argv[3])


#parseProcDiskStatLog(2, sys.argv[4])

#print 'Test'







