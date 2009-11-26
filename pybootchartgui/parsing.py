#  This file is part of pybootchartgui.

#  pybootchartgui is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  pybootchartgui is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with pybootchartgui. If not, see <http://www.gnu.org/licenses/>.


from __future__ import with_statement

import os
import string
import re
import tarfile
from time import *
from collections import defaultdict

from samples import *
from process_tree import ProcessTree

class ParseError(Exception):
	"""Represents errors during parse of the bootchart."""
	def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value

def _parse_headers(file):
	"""Parses the headers of the bootchart."""
        def parse((headers,last), line): 
            if '=' in line: last,value = map(string.strip, line.split('=', 1))
            else:           value = line.strip()
            headers[last] += value
            return headers,last
        return reduce(parse, file.read().split('\n'), (defaultdict(str),''))[0]

def _parse_timed_blocks(file):
	"""Parses (ie., splits) a file into so-called timed-blocks. A
        timed-block consists of a timestamp on a line by itself followed
        by zero or more lines of data for that point in time."""
        def parse(block):
            lines = block.split('\n')
            if not lines:
                raise ParseError('expected a timed-block consisting a timestamp followed by data lines')
            try:
                return (int(lines[0]), lines[1:])
            except ValueError:
                raise ParseError("expected a timed-block, but timestamp '%s' is not an integer" % lines[0])
	blocks = file.read().split('\n\n')
        return [parse(block) for block in blocks if block.strip() and not block.endswith(' not running\n')]
	
def _parse_proc_ps_log(writer, file):
	"""
	 * See proc(5) for details.
	 * 
	 * {pid, comm, state, ppid, pgrp, session, tty_nr, tpgid, flags, minflt, cminflt, majflt, cmajflt, utime, stime,
	 *  cutime, cstime, priority, nice, 0, itrealvalue, starttime, vsize, rss, rlim, startcode, endcode, startstack, 
	 *  kstkesp, kstkeip}
	"""
	processMap = {}
	ltime = 0
        timed_blocks = _parse_timed_blocks(file)
	for time, lines in timed_blocks:
		for line in lines:
			if line is '': continue
			tokens = line.split(' ')

			offset = [index for index, token in enumerate(tokens[1:]) if token[-1] == ')'][0]		
			pid, cmd, state, ppid = int(tokens[0]), ' '.join(tokens[1:2+offset]), tokens[2+offset], int(tokens[3+offset])
			userCpu, sysCpu, stime= int(tokens[13+offset]), int(tokens[14+offset]), int(tokens[21+offset])

			if pid in processMap:
				process = processMap[pid]
				process.cmd = cmd.strip('()') # why rename after latest name??
			else:
				process = Process(writer, pid, cmd.strip('()'), ppid, min(time, stime))
				processMap[pid] = process
			
			if process.last_user_cpu_time is not None and process.last_sys_cpu_time is not None and ltime is not None:
				userCpuLoad, sysCpuLoad = process.calc_load(userCpu, sysCpu, time - ltime)
				cpuSample = CPUSample('null', userCpuLoad, sysCpuLoad, 0.0)
				process.samples.append(ProcessSample(time, state, cpuSample))
			
			process.last_user_cpu_time = userCpu
			process.last_sys_cpu_time = sysCpu
		ltime = time

	startTime = timed_blocks[0][0]
	avgSampleLength = (ltime - startTime)/(len(timed_blocks)-1)	

	for process in processMap.values():
		process.set_parent(processMap)

	for process in processMap.values():
		process.calc_stats(avgSampleLength)
		
	writer.info("%d samples, avg. sample length %f" % (len(timed_blocks), avgSampleLength))
	writer.info("process list size: %d" % len(processMap.values()))
	return ProcessStats(processMap.values(), avgSampleLength, startTime, ltime)

def _parse_taskstats_log(writer, file):
	"""
	 * See bootchart-collector.c for details.
	 * 
	 * { pid, ppid, comm, cpu_run_real_total, blkio_delay_total, swapin_delay_total }
	 *
	"""
	processMap = {}
	pidRewrites = {}
	ltime = None
        timed_blocks = _parse_timed_blocks(file)
	for time, lines in timed_blocks:
		# we have no 'stime' from taskstats, so prep 'init'
		if ltime is None:
			process = Process(writer, 1, 'init', 0, 0)
			processMap[1] = process
			ltime = time
#			continue
		for line in lines:
			if line is '': continue
			tokens = line.split(' ')

			opid, ppid, cmd = float(tokens[0]), int(tokens[1]), tokens[2]
			cpu_ns, blkio_delay_ns, swapin_delay_ns = long(tokens[3]), long(tokens[4]), long(tokens[5]),

			# when the process name changes, we re-write the pid.
			if pidRewrites.has_key(opid):
				pid = pidRewrites[opid];
			else:
				pid = opid;

			cmd = cmd.strip('(').strip(')')
			if pid in processMap:
				process = processMap[pid]
				if process.cmd != cmd:
					pid += 0.001
					pidRewrites[opid] = pid;
#					print "process mutation ! '%s' vs '%s' pid %s -> pid %s\n" % (process.cmd, cmd, opid, pid)
					process = Process(writer, pid, cmd, ppid, time)
					processMap[pid] = process
				else:
					process.cmd = cmd;
			else:
				process = Process(writer, pid, cmd, ppid, time)
				processMap[pid] = process

			delta_cpu_ns = (int) (cpu_ns - process.last_cpu_ns)
			delta_blkio_delay_ns = (int) (blkio_delay_ns - process.last_blkio_delay_ns)
			delta_swapin_delay_ns = (int) (swapin_delay_ns - process.last_swapin_delay_ns)

			# make up some state data ...
			if delta_cpu_ns > 0:
				state = "R"
			elif delta_blkio_delay_ns + delta_swapin_delay_ns > 0:
				state = "D"
			else:
				state = "S"

			interval_in_ns = 1000000.0 * (time - ltime) # ms to ns
			if interval_in_ns == 0:
				interval_in_ns = 1

			# hackley nastiness - we want to show these more clearly / sensibly
			if delta_cpu_ns + delta_blkio_delay_ns + delta_swapin_delay_ns > 0:
				cpuSample = CPUSample('null', delta_cpu_ns / interval_in_ns, 0.0,
						      delta_blkio_delay_ns / interval_in_ns,
						      delta_swapin_delay_ns / interval_in_ns)
			process.samples.append(ProcessSample(time, state, cpuSample))
			
			process.last_cpu_ns = cpu_ns
			process.last_blkio_delay_ns = blkio_delay_ns
			process.last_swapin_delay_ns = swapin_delay_ns
		ltime = time

	startTime = timed_blocks[0][0]
	avgSampleLength = (ltime - startTime)/(len(timed_blocks)-1)	

	for process in processMap.values():
		process.set_parent(processMap)

	for process in processMap.values():
		process.calc_stats(avgSampleLength)
		
	return ProcessStats(processMap.values(), avgSampleLength, startTime, ltime)
	
def _parse_proc_stat_log(file):
	samples = []
	ltimes = None
	for time, lines in _parse_timed_blocks(file):
		# CPU times {user, nice, system, idle, io_wait, irq, softirq}
		tokens = lines[0].split();
		times = [ int(token) for token in tokens[1:] ]
		if ltimes:
			user = float((times[0] + times[1]) - (ltimes[0] + ltimes[1]))
			system = float((times[2] + times[5] + times[6]) - (ltimes[2] + ltimes[5] + ltimes[6]))
			idle = float(times[3] - ltimes[3])
			iowait = float(times[4] - ltimes[4])
			
			aSum = max(user + system + idle + iowait, 1)
			samples.append( CPUSample(time, user/aSum, system/aSum, iowait/aSum) )
		
		ltimes = times		
		# skip the rest of statistics lines
	return samples

		
def _parse_proc_disk_stat_log(file, numCpu):
	"""
	Parse file for disk stats, but only look at the whole disks, eg. sda,
	not sda1, sda2 etc. The format of relevant lines should be:
	{major minor name rio rmerge rsect ruse wio wmerge wsect wuse running use aveq}
	"""
	DISK_REGEX = 'hd.$|sd.$|vd.$'
	
	def is_relevant_line(linetokens):
		return len(linetokens) == 14 and re.match(DISK_REGEX, linetokens[2])
	
	disk_stat_samples = []

	for time, lines in _parse_timed_blocks(file):
		sample = DiskStatSample(time)		
		relevant_tokens = [linetokens for linetokens in map(string.split,lines) if is_relevant_line(linetokens)]
		
		for tokens in relevant_tokens:
			disk, rsect, wsect, use = tokens[2], int(tokens[5]), int(tokens[9]), int(tokens[12])			
			sample.add_diskdata([rsect, wsect, use])
		
		disk_stat_samples.append(sample)
			
	disk_stats = []
	for sample1, sample2 in zip(disk_stat_samples[:-1], disk_stat_samples[1:]):
		interval = sample1.time - sample2.time
		sums = [ a - b for a, b in zip(sample1.diskdata, sample2.diskdata) ]
		readTput = sums[0] / 2.0 * 100.0 / interval
		writeTput = sums[1] / 2.0 * 100.0 / interval
		util = float( sums[2] ) / 10 / interval / numCpu
		util = max(0.0, min(1.0, util))
		disk_stats.append(DiskSample(sample2.time, readTput, writeTput, util))
	
	return disk_stats

# if we boot the kernel with: initcall_debug printk.time=1 we can
# get all manner of interesting data from the dmesg output
# We turn this into a pseudo-process tree: each event is
# characterised by a 
# we don't try to detect a "kernel finished" state - since the kernel
# continues to do interesting things after init is called.
#
# sample input:
# [    0.000000] ACPI: FACP 3f4fc000 000F4 (v04 INTEL  Napa     00000001 MSFT 01000013)
# ...
# [    0.039993] calling  migration_init+0x0/0x6b @ 1
# [    0.039993] initcall migration_init+0x0/0x6b returned 1 after 0 usecs
def _parse_dmesg(writer, file):
	timestamp_re = re.compile ("^\[\S*([^\]]*)\S*]\s+(.*)$")
	split_re = re.compile ("^(\S+)\s+([\S\+_-]+) (.*)$")
	processMap = {}
	idx = 0
	inc = 1.0 / 1000000
	kernel = Process(writer, idx, "k-boot", 0, 0.1)
	processMap['k-boot'] = kernel
	for line in file.read().split('\n'):
		t = timestamp_re.match (line)
		if t is None:
#			print "duff timestamp " + line
			continue

		time_ms = float (t.group(1)) * 1000
		m = split_re.match (t.group(2))

		if m is None:
			continue
#	        print "match: '%s'" % (m.group(1))
		type = m.group(1)
		func = m.group(2)
		rest = m.group(3)

		if t.group(2).startswith ('Write protecting the') or \
		   t.group(2).startswith ('Freeing unused kernel memory'):
			kernel.duration = time_ms / 10
			continue

#	        print "foo: '%s' '%s' '%s' '%s'" % (timestamp, type, func, rest)
		if type == "calling":
			ppid = kernel.pid
			p = re.match ("\@ (\d+)", rest)
			if p is not None:
				ppid = float (p.group(1)) / 1000
#				print "match: '%s' ('%g') at '%s'" % (func, ppid, time_ms)
			name = func.split ('+', 1) [0]
			idx += inc
			processMap[func] = Process(writer, ppid + idx, name, ppid, time_ms / 10)
		elif type == "initcall":
#			print "finished: '%s' at '%s'" % (func, time_ms)
			process = processMap[func]
			process.duration = (time_ms / 10) - process.start_time
				
		elif type == "async_waiting" or type == "async_continuing":
			continue # ignore

	return processMap.values()

# read LE int32
def _read_le_int32(file):
	bytes = file.read(4)
	return (ord(bytes[0]))       | (ord(bytes[1]) << 8) | \
	       (ord(bytes[2]) << 16) | (ord(bytes[3]) << 24)
	
#
# Parse binary pacct accounting file output
# cf. /usr/include/linux/acct.h
#
# FIXME - we don't (yet) use this ... really instead
# of this it would be nice to know who forked a process,
# rather than (per-se) it's self-selected parent.
#
def _parse_pacct(writer, file):
	pidMap = {}
	pidMap[0] = 0

	while file.read(1) != "": # ignore flags
		ver = file.read(1)
		if ord(ver) < 3:
			print "Invalid version 0x%x" % (ord(ver))
			return None

		file.seek (14, 1)     # user, group etc.
		pid = _read_le_int32 (file)
		ppid = _read_le_int32 (file)
#		print "Parent of %d is %d" % (pid, ppid)
		pidMap[pid] = ppid
		file.seek (4 + 4 + 16, 1) # timings
		file.seek (16, 1)         # acct_comm
		
	return pidMap;

def get_num_cpus(headers):
    """Get the number of CPUs from the system.cpu header property. As the
    CPU utilization graphs are relative, the number of CPUs currently makes
    no difference."""
    if headers is None:
        return 1
    cpu_model = headers.get("system.cpu")
    if cpu_model is None:
        return 1
    mat = re.match(".*\\((\\d+)\\)", cpu_model)
    if mat is None:
        return 1
    return int(mat.group(1))

class ParserState:
    def __init__(self):
        self.headers = None
	self.disk_stats = None
	self.ps_stats = None
	self.cpu_stats = None

    def valid(self):
        return self.headers != None and self.disk_stats != None and self.ps_stats != None and self.cpu_stats != None


_relevant_files = set(["header", "proc_diskstats.log", "proc_ps.log", "proc_stat.log"])

def _do_parse(writer, state, name, file):
    writer.status("parsing '%s'" % name)
    t1 = clock()
    if name == "header":
        state.headers = _parse_headers(file)
    elif name == "proc_diskstats.log":
        state.disk_stats = _parse_proc_disk_stat_log(file, get_num_cpus(state.headers))
    elif name == "proc_ps.log":
        state.ps_stats = _parse_proc_ps_log(writer, file)
    elif name == "taskstats.log":
        state.ps_stats = _parse_taskstats_log(writer, file)
    elif name == "proc_stat.log":
        state.cpu_stats = _parse_proc_stat_log(file)
    elif name == "dmesg":
       state.kernel = _parse_dmesg(writer, file)
    elif name == "kernel_pacct":
       state.pacct = _parse_pacct(writer, file)
    t2 = clock()
    writer.info("  %s seconds" % str(t2-t1))
    return state

def parse_file(writer, state, filename):
    basename = os.path.basename(filename)
    if not(basename in _relevant_files):
        writer.info("ignoring '%s' as it is not relevant" % filename)
        return state
    with open(filename, "rb") as file:
        return _do_parse(writer, state, basename, file)

def parse_paths(writer, state, paths):
    for path in paths:
        root,extension = os.path.splitext(path)
        if not(os.path.exists(path)):
            writer.warn("warning: path '%s' does not exist, ignoring." % path)
            continue
        if os.path.isdir(path):
            files = [ f for f in [os.path.join(path, f) for f in os.listdir(path)] if os.path.isfile(f) ]
            files.sort()
            state = parse_paths(writer, state, files)
        elif extension in [".tar", ".tgz", ".gz"]:
            if extension == ".gz":
                root,extension = os.path.splitext(root)
                if extension != ".tar":
                    writer.warn("warning: can only handle zipped tar files, not zipped '%s'-files; ignoring" % extension)
                    continue
            tf = None
            try:
                writer.status("parsing '%s'" % path)
                tf = tarfile.open(path, 'r:*')
                for name in tf.getnames():
                    state = _do_parse(writer, state, name, tf.extractfile(name))
            except tarfile.ReadError, error:
                raise ParseError("error: could not read tarfile '%s': %s." % (path, error))
            finally:
                if tf != None:
                    tf.close()
        else:
            state = parse_file(writer, state, path)
    return state

def crop(writer, crop_after, state):
    names = [x[:15] for x in crop_after.split(",")]
    for proc in state.ps_stats.process_list:
        if proc.cmd in names:
            writer.info("selected proc '%s' from list (start %d)"
			% (proc.cmd, proc.start_time))
	    break
    else:
        writer.info("no selected proc in list")
        return

    def is_idle_at(util, start, j):
        k = j + 1
	while k < len(util) and util[k][0] < start + 300:
            k += 1
	k = min(k, len(util)-1)

	if util[j][1] >= 0.25:
            return False

	avgload = sum(u[1] for u in util[j:k+1]) / (k-j+1)
	if avgload < 0.25:
            return True
	else:
            return False
    def is_idle(util, start):
        for j in range(0, len(util)):
            if util[j][0] < start:
                continue
	    return is_idle_at(util, start, j)
	else:
            return False

    cpu_util = [(sample.time, sample.user + sample.sys + sample.io) for sample in state.cpu_stats]
    disk_util = [(sample.time, sample.util) for sample in state.disk_stats]

    for i in range(0, len(cpu_util)):
        if cpu_util[i][0] < proc.start_time:
            continue
	if is_idle_at(cpu_util, cpu_util[i][0], i) \
	   and is_idle(disk_util, cpu_util[i][0]):
            idle = cpu_util[i][0]
	    break
    else:
        writer.info("selected proc not found in tree")
        return

    crop = idle + 300
    writer.info("cropping at time %d" % crop)
    while len(state.cpu_stats) \
		and state.cpu_stats[-1].time > crop:
        state.cpu_stats.pop()
    while len(state.disk_stats) \
		and state.disk_stats[-1].time > crop:
        state.disk_stats.pop()

    state.ps_stats.end_time = crop
    while len(state.ps_stats.process_list) \
		and state.ps_stats.process_list[-1].start_time > crop:
        state.ps_stats.process_list.pop()
    for proc in state.ps_stats.process_list:
        proc.duration=min(proc.duration,crop-proc.start_time)
	while len(proc.samples) \
		    and proc.samples[-1].time >crop:
            proc.samples.pop()

    return idle


def parse(writer, paths, prune, crop_after, annotate):
    state = parse_paths(writer, ParserState(), paths)
    if not state.valid():
        raise ParseError("empty state: '%s' does not contain a valid bootchart" % ", ".join(paths))

    # Crop the chart to the end of the first idle period after the given
    # process
    if crop_after:
        idle = crop(writer, crop_after, state)
    else:
        idle = None
    # Annotate other times as the first start point of given process lists
    times = [ idle ]
    if annotate:
        for procnames in annotate:
            names = [x[:15] for x in procnames.split(",")]
	    for x in names:
		    print "Names: '%s'" % (x);
            for proc in state.ps_stats.process_list:
                if proc.cmd in names:
		    times.append(proc.start_time)
		    break
	    else:
                times.append(None)

    monitored_app = state.headers.get("profile.process")
    proc_tree = ProcessTree(writer, state.kernel, state.ps_stats, monitored_app, prune, idle)
    return (state.headers, state.cpu_stats, state.disk_stats, proc_tree, times)
