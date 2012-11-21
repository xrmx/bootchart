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
from time import clock
from collections import defaultdict
from functools import reduce

from .samples import *
from .process_tree import ProcessTree

# Parsing produces as its end result a 'Trace'

class Trace:
    def __init__(self, writer, paths, options):
        self.headers = None
        self.disk_stats = None
        self.ps_stats = None
        self.taskstats = None
        self.cpu_stats = None
        self.events = None
        self.cmdline = None
        self.kernel = None
        self.kernel_tree = None
        self.filename = None
        self.parent_map = None
        self.mem_stats = None

        # Read in all files, parse each into a time-ordered list
        parse_paths (writer, self, paths, options)
        if not self.valid():
            raise ParseError("empty state: '%s' does not contain a valid bootchart" % ", ".join(paths))

        # Turn that parsed information into something more useful
        # link processes into a tree of pointers, calculate statistics
        self.adorn_process_map(writer, options)

        # Crop the chart to the end of the first idle period after the given
        # process
        if options.crop_after:
            idle = self.crop (writer, options.crop_after)
        else:
            idle = None

        # Annotate other times as the first start point of given process lists
        self.times = [ idle ]
        if options.annotate:
            for procnames in options.annotate:
                names = [x[:15] for x in procnames.split(",")]
                for proc in self.ps_stats.process_map.values():
                    if proc.cmd in names:
                        self.times.append(proc.start_time)
                        break
                    else:
                        self.times.append(None)

        self.proc_tree = ProcessTree(writer, self.kernel, self.ps_stats,
                                     self.ps_stats.sample_period,
                                     self.headers.get("profile.process"),
                                     options.prune, idle, self.taskstats,
                                     self.parent_map is not None)

        if self.kernel is not None:
            self.kernel_tree = ProcessTree(writer, self.kernel, None, 0,
                                           self.headers.get("profile.process"),
                                           False, None, None, True)

    def valid(self):
        return self.headers != None and self.disk_stats != None and \
               self.ps_stats != None and self.cpu_stats != None

    def adorn_process_map(self, writer, options):

        def find_parent_id_for(pid):
            if pid is 0:
                return 0
            ppid = self.parent_map.get(pid)
            if ppid:
                # many of these double forks are so short lived
                # that we have no samples, or process info for them
                # so climb the parent hierarcy to find one
                if int (ppid * 1000) not in self.ps_stats.process_map:
#                    print "Pid '%d' short lived with no process" % ppid
                    ppid = find_parent_id_for (ppid)
#                else:
#                    print "Pid '%d' has an entry" % ppid
            else:
#                print "Pid '%d' missing from pid map" % pid
                return 0
            return ppid

        # merge in the cmdline data
        if self.cmdline is not None:
            for proc in self.ps_stats.process_map.values():
                rpid = int (proc.pid / 1000)
                if rpid in self.cmdline:
                    cmd = self.cmdline[rpid]
                    proc.exe = cmd['exe']
                    proc.args = cmd['args']
#                else:
#                    print "proc %d '%s' not in cmdline" % (rpid, proc.exe)

        if options.synthesize_sample_start_events:
            init_pid = 1
            key = init_pid * 1000
            proc = self.ps_stats.process_map[key]
            for cpu in self.cpu_stats:
                # assign to the init process's bar, for lack of any better
                ev = EventSample(cpu.time, cpu.time*10*1000, init_pid, init_pid,
                                 "comm", "func_file_line", None)
                proc.events.append(ev)

        # merge in events
        if self.events is not None:
            for ev in self.events:
                if ev.time > self.ps_stats.end_time:
                    continue
                key = int(ev.tid) * 1000
                if key in self.ps_stats.process_map:
                    self.ps_stats.process_map[key].events.append(ev)
                else:
                    writer.warn("no samples of /proc/%d/task/%d/proc found -- event lost:\n\t%s" %
                                (ev.pid, ev.tid, ev.raw_log_line))

        # re-parent any stray orphans if we can
        if self.parent_map is not None:
            for process in self.ps_stats.process_map.values():
                ppid = find_parent_id_for (int(process.pid / 1000))
                if ppid:
                    process.ppid = ppid * 1000

        # Init the upward "parent" pointers.
        # Downward child pointers stored in a list -- remains empty until the ProcessTree is inited.
        for process in self.ps_stats.process_map.values():
            process.set_parent (self.ps_stats.process_map)

        # count on fingers variously
        for process in self.ps_stats.process_map.values():
            process.calc_stats (self.ps_stats.sample_period)

    def crop(self, writer, crop_after):

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

        names = [x[:15] for x in crop_after.split(",")]
        for proc in self.ps_stats.process_map.values():
            if proc.cmd in names or proc.exe in names:
                writer.info("selected proc '%s' from list (start %d)"
                            % (proc.cmd, proc.start_time))
                break
        if proc is None:
            writer.warn("no selected crop proc '%s' in list" % crop_after)


        cpu_util = [(sample.time, sample.user + sample.sys + sample.io) for sample in self.cpu_stats]
        disk_util = [(sample.time, sample.util) for sample in self.disk_stats]

        idle = None
        for i in range(0, len(cpu_util)):
            if cpu_util[i][0] < proc.start_time:
                continue
            if is_idle_at(cpu_util, cpu_util[i][0], i) \
               and is_idle(disk_util, cpu_util[i][0]):
                idle = cpu_util[i][0]
                break

        if idle is None:
            writer.warn ("not idle after proc '%s'" % crop_after)
            return None

        crop_at = idle + 300
        writer.info ("cropping at time %d" % crop_at)
        while len (self.cpu_stats) \
                    and self.cpu_stats[-1].time > crop_at:
            self.cpu_stats.pop()
        while len (self.disk_stats) \
                    and self.disk_stats[-1].time > crop_at:
            self.disk_stats.pop()

        self.ps_stats.end_time = crop_at

        cropped_map = {}
        for key, value in self.ps_stats.process_map.items():
            if (value.start_time <= crop_at):
                cropped_map[key] = value

        for proc in cropped_map.values():
            proc.duration = min (proc.duration, crop_at - proc.start_time)
            while len (proc.samples) \
                        and proc.samples[-1].time > crop_at:
                proc.samples.pop()

        self.ps_stats.process_map = cropped_map

        return idle



class ParseError(Exception):
    """Represents errors during parse of the bootchart."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return self.value

def _parse_headers(file):
    """Parses the headers of the bootchart."""
    def parse(acc, line):
        (headers, last) = acc
        if '=' in line:
            last, value = map (lambda x: x.strip(), line.split('=', 1))
        else:
            value = line.strip()
        headers[last] += value
        return headers, last
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

def _parse_proc_ps_log(options, writer, file):
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
            if len(tokens) < 21:
                continue

            offset = [index for index, token in enumerate(tokens[1:]) if token[-1] == ')'][0]
            pid, cmd, state, ppid = int(tokens[0]), ' '.join(tokens[1:2+offset]), tokens[2+offset], int(tokens[3+offset])
            userCpu, sysCpu, starttime = int(tokens[13+offset]), int(tokens[14+offset]), int(tokens[21+offset])

            # magic fixed point-ness ...
            pid *= 1000
            ppid *= 1000
            if pid in processMap:
                process = processMap[pid]
                process.cmd = cmd.strip('()') # why rename after latest name??
            else:
                if time < starttime:
                    # large values signify a collector problem, e.g. resource starvation
                    writer.status("time (%d) < starttime (%d), diff %d -- PID %d" %
                                  (time, starttime, time-starttime, pid/1000))

                process = Process(writer, pid, pid, cmd.strip('()'), ppid, starttime)
                processMap[pid] = process

            if process.last_user_cpu_time is not None and process.last_sys_cpu_time is not None:
                if ltime is None:
                    userCpuLoad, sysCpuLoad = 0, 0
                else:
                    userCpuLoad, sysCpuLoad = process.calc_load(userCpu, sysCpu, max(1, time - ltime))
                cpuSample = ProcessCPUSample('null', userCpuLoad, sysCpuLoad, 0.0, 0.0)
                process.samples.append(ProcessSample(time, state, cpuSample))

            process.last_user_cpu_time = userCpu
            process.last_sys_cpu_time = sysCpu
        ltime = time

    if len (timed_blocks) < 2:
        return None

    startTime = timed_blocks[0][0]
    avgSampleLength = (ltime - startTime)/(len (timed_blocks) - 1)

    return ProcessStats (writer, processMap, len (timed_blocks), avgSampleLength, startTime, ltime)

def _parse_proc_ps_threads_log(options, writer, file):
    """
     *    0* pid -- inserted here from value in /proc/*pid*/task/.  Not to be found in /proc/*pid*/task/*tid*/stat.
     *              Not the same as pgrp, session, or tpgid.  Refer to collector daemon source code for details.
     *    1  tid
     *    2  comm
     *    3  state
     *    4  ppid
     *    5  flags
     *    6  majflt
     *    7  utime
     *    8  stime
     *    9  cutime
     *   10  cstime
     *   11  priority
     *   12  nice
     *   13  time_in_jiffies_the_process_started_after_system_boot
     *   14  current_EIP_instruction_pointer
     *   15  wchan
     *   16  scheduling_policy
    """
    processMap = {}
    ltime = 0
    timed_blocks = _parse_timed_blocks(file)
    for time, lines in timed_blocks:
        for line in lines:
            if line is '': continue
            tokens = line.split(' ')
            if len(tokens) < 17:
                writer.status("misformatted line at time {0:d}:\n\t{1:s}".format(time,line))
                continue

            offset = [index for index, token in enumerate(tokens[2:]) if (len(token) > 0 and token[-1] == ')')][0]
            pid, tid, cmd, state, ppid = int(tokens[0]), int(tokens[1]), ' '.join(tokens[2:3+offset]), tokens[3+offset], int(tokens[4+offset])
            userCpu, sysCpu, starttime = int(tokens[7+offset]), int(tokens[8+offset]), int(tokens[13+offset])

            # magic fixed point-ness ...
            tid *= 1000
            pid *= 1000
            ppid *= 1000
            if tid in processMap:
                process = processMap[tid]
                process.cmd = cmd.strip('()') # why rename after latest name??
            else:
                if time < starttime:
                    # large values signify a collector problem, e.g. resource starvation
                    writer.status("time (%dcs) < starttime (%dcs), diff %d -- TID %d" %
                                  (time, starttime, time-starttime, tid/1000))

                process = Process(writer, pid, tid, cmd.strip('()'), ppid, starttime)
                processMap[tid] = process

            if process.last_user_cpu_time is not None and process.last_sys_cpu_time is not None:
                if ltime is None:
                    userCpuLoad, sysCpuLoad = 0, 0
                else:
                    userCpuLoad, sysCpuLoad = process.calc_load(userCpu, sysCpu, max(1, time - ltime))
                cpuSample = ProcessCPUSample('null', userCpuLoad, sysCpuLoad, 0.0, 0.0)
                process.samples.append(ProcessSample(time, state, cpuSample))

            process.last_user_cpu_time = userCpu
            process.last_sys_cpu_time = sysCpu
        ltime = time

    if len (timed_blocks) < 2:
        return None

    startTime = timed_blocks[0][0]
    avgSampleLength = (ltime - startTime)/(len (timed_blocks) - 1)

    return ProcessStats (writer, processMap, len (timed_blocks), avgSampleLength, startTime, ltime)

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
        # we have no 'starttime' from taskstats, so prep 'init'
        if ltime is None:
            process = Process(writer, 1, '[init]', 0, 0)
            processMap[1000] = process
            ltime = time
#                       continue
        for line in lines:
            if line is '': continue
            tokens = line.split(' ')

            opid, ppid, cmd = int(tokens[0]), int(tokens[1]), tokens[2]
            cpu_ns, blkio_delay_ns, swapin_delay_ns = long(tokens[-3]), long(tokens[-2]), long(tokens[-1]),

            # make space for trees of pids
            opid *= 1000
            ppid *= 1000

            # when the process name changes, we re-write the pid.
            if opid in pidRewrites:
                pid = pidRewrites[opid]
            else:
                pid = opid

            cmd = cmd.strip('(').strip(')')
            if pid in processMap:
                process = processMap[pid]
                if process.cmd != cmd:
                    pid += 1
                    pidRewrites[opid] = pid
#                                       print "process mutation ! '%s' vs '%s' pid %s -> pid %s\n" % (process.cmd, cmd, opid, pid)
                    process = process.split (writer, pid, cmd, ppid, time)
                    processMap[pid] = process
                else:
                    process.cmd = cmd;
            else:
                process = Process(writer, pid, cmd, ppid, time)
                processMap[pid] = process

            delta_cpu_ns = (float) (cpu_ns - process.last_cpu_ns)
            delta_blkio_delay_ns = (float) (blkio_delay_ns - process.last_blkio_delay_ns)
            delta_swapin_delay_ns = (float) (swapin_delay_ns - process.last_swapin_delay_ns)

            # make up some state data ...
            if delta_cpu_ns > 0:
                state = "R"
            elif delta_blkio_delay_ns + delta_swapin_delay_ns > 0:
                state = "D"
            else:
                state = "S"

            # retain the ns timing information into a ProcessCPUSample - that tries
            # with the old-style to be a %age of CPU used in this time-slice.
            if delta_cpu_ns + delta_blkio_delay_ns + delta_swapin_delay_ns > 0:
#                               print "proc %s cpu_ns %g delta_cpu %g" % (cmd, cpu_ns, delta_cpu_ns)
                cpuSample = ProcessCPUSample('null', delta_cpu_ns, 0.0,
                                      delta_blkio_delay_ns,
                                      delta_swapin_delay_ns)
                process.samples.append(ProcessSample(time, state, cpuSample))

            process.last_cpu_ns = cpu_ns
            process.last_blkio_delay_ns = blkio_delay_ns
            process.last_swapin_delay_ns = swapin_delay_ns
        ltime = time

    if len (timed_blocks) < 2:
        return None

    startTime = timed_blocks[0][0]
    avgSampleLength = (ltime - startTime)/(len(timed_blocks)-1)

    return ProcessStats (writer, processMap, len (timed_blocks), avgSampleLength, startTime, ltime)

def _parse_proc_stat_log(file):
    samples = []
    ltimes = None
    for time, lines in _parse_timed_blocks(file):
        # skip empty lines
        if not lines:
            continue
        # CPU times {user, nice, system, idle, io_wait, irq, softirq} summed over all cores.
        tokens = lines[0].split()
        times = [ int(token) for token in tokens[1:] ]
        if ltimes:
            user = float((times[0] + times[1]) - (ltimes[0] + ltimes[1]))
            system = float((times[2] + times[5] + times[6]) - (ltimes[2] + ltimes[5] + ltimes[6]))
            idle = float(times[3] - ltimes[3])
            iowait = float(times[4] - ltimes[4])
            aSum = max(user + system + idle + iowait, 1)

        procs_running = 0
        procs_blocked = 0
        for line in lines:
            tokens = line.split()
            if tokens[0] == 'procs_running':
                procs_running = int(tokens[1])
            if tokens[0] == 'procs_blocked':
                procs_blocked = int(tokens[1])
        if ltimes:
            samples.append( SystemCPUSample(time, user/aSum, system/aSum, iowait/aSum, procs_running, procs_blocked) )
        else:
            samples.append( SystemCPUSample(time, 0.0, 0.0, 0.0, procs_running, procs_blocked) )
        ltimes = times
    return samples

def _parse_proc_disk_stat_log(file, options, numCpu):
    """
    Parse file for disk stats, summing over all physical storage devices, eg. sda, sdb.
    Also parse stats for individual devices or partitions indicated on the command line.
    The format of relevant lines should be:
    {major minor name rio rmerge rsect ruse wio wmerge wsect wuse running io_ticks aveq}
    The file is generated by block/genhd.c
    FIXME: for Flash devices, rio/wio may have more usefulness than rsect/wsect.
    """

    def delta_disk_samples(disk_stat_samples, numCpu):
        disk_stats = []

        # Very short intervals amplify round-off under division by time delta, so coalesce now.
        # XX  scaling issue for high-efficiency collector!
        disk_stat_samples_coalesced = [(disk_stat_samples[0])]
        for sample in disk_stat_samples:
            if sample.time - disk_stat_samples_coalesced[-1].time < 5:
                continue
            disk_stat_samples_coalesced.append(sample)

        for sample1, sample2 in zip(disk_stat_samples_coalesced[:-1], disk_stat_samples_coalesced[1:]):
            interval = sample2.time - sample1.time
            vector_diff = [ a - b for a, b in zip(sample2.diskdata, sample1.diskdata) ]
            readTput =  float( vector_diff[0]) / interval
            writeTput = float( vector_diff[1]) / interval
            util = float( vector_diff[2]) / 10 / interval / numCpu
            disk_stats.append(DiskSample(sample2.time, readTput, writeTput, util))
        return disk_stats

    def get_relevant_tokens(lines, regex):
        return [
            linetokens
            for linetokens in map (lambda x: x.split(),lines)
            	if len(linetokens) == 14 and regex.match(linetokens[2])
            ]

    def add_tokens_to_sample(sample, tokens):
        if options.show_ops_not_bytes:
            disk_name, rop, wop, io_ticks = tokens[2], int(tokens[3]), int(tokens[7]), int(tokens[12])
            sample.add_diskdata([rop, wop, io_ticks])
        else:
            disk_name, rsect, wsect, io_ticks = tokens[2], int(tokens[3]), int(tokens[7]), int(tokens[12])
            sample.add_diskdata([rsect, wsect, io_ticks])
        return disk_name

    # matched not against whole line, but field only
    disk_regex_re = re.compile('^([hsv]d.|mtdblock\d|mmcblk\d|cciss/c\d+d\d+.*)$')

    disk_stat_samples = []
    for time, lines in _parse_timed_blocks(file):
        sample = DiskStatSample(time)
        relevant_tokens = get_relevant_tokens(lines, disk_regex_re)

        for tokens in relevant_tokens:
            add_tokens_to_sample(sample,tokens)

        disk_stat_samples.append(sample)

    partition_samples = [DiskSamples("Sum over all disks",
                                     delta_disk_samples(disk_stat_samples, numCpu))]

    strip_slash_dev_slash = re.compile("/dev/(.*)$")
    if options.partitions:
        for part in options.partitions:
                file.seek(0)
                disk_stat_samples = []
                this_partition_regex_re = re.compile('^' + part + '.*$')
                disk_name = ''

                # for every timed_block
                disk_stat_samples = []
                for time, lines in _parse_timed_blocks(file):
                    sample = DiskStatSample(time)
                    relevant_tokens = get_relevant_tokens(lines, this_partition_regex_re)
                    if relevant_tokens:    # XX  should exit with usage message
                        disk_name = add_tokens_to_sample(sample,relevant_tokens[0]) # [0] assumes 'part' matched at most a single line
                    disk_stat_samples.append(sample)

                if options.partition_labels:
                    disk_name = options.partition_labels[0]
                    options.partition_labels = options.partition_labels[1:]
                partition_samples.append(DiskSamples(disk_name,
                                                     delta_disk_samples(disk_stat_samples, numCpu)))

    return partition_samples

def _parse_proc_meminfo_log(file):
    """
    Parse file for global memory statistics.
    The format of relevant lines should be: ^key: value( unit)?
    """
    used_values = ('MemTotal', 'MemFree', 'Buffers', 'Cached', 'SwapTotal', 'SwapFree',)

    mem_stats = []
    meminfo_re = re.compile(r'([^ \t:]+):\s*(\d+).*')

    for time, lines in _parse_timed_blocks(file):
        sample = MemSample(time)

        for line in lines:
            match = meminfo_re.match(line)
            if not match:
                raise ParseError("Invalid meminfo line \"%s\"" % match.groups(0))
            if match.group(1) in used_values:
                sample.add_value(match.group(1), int(match.group(2)))

        mem_stats.append(sample)

    return mem_stats

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
    timestamp_re = re.compile ("^\[\s*(\d+\.\d+)\s*]\s+(.*)$")
    split_re = re.compile ("^(\S+)\s+([\S\+_-]+) (.*)$")
    processMap = {}
    idx = 0
    inc = 1.0 / 1000000
    kernel = Process(writer, idx, "k-boot", 0, 0.1)
    processMap['k-boot'] = kernel
    base_ts = False
    max_ts = 0
    for line in file.read().split('\n'):
        t = timestamp_re.match (line)
        if t is None:
#                       print "duff timestamp " + line
            continue

        time_ms = float (t.group(1)) * 1000
        # looks like we may have a huge diff after the clock
        # has been set up. This could lead to huge graph:
        # so huge we will be killed by the OOM.
        # So instead of using the plain timestamp we will
        # use a delta to first one and skip the first one
        # for convenience
        if max_ts == 0 and not base_ts and time_ms > 1000:
            base_ts = time_ms
            continue
        max_ts = max(time_ms, max_ts)
        if base_ts:
#                       print "fscked clock: used %f instead of %f" % (time_ms - base_ts, time_ms)
            time_ms -= base_ts
        m = split_re.match (t.group(2))

        if m is None:
            continue
#               print "match: '%s'" % (m.group(1))
        type = m.group(1)
        func = m.group(2)
        rest = m.group(3)

        if t.group(2).startswith ('Write protecting the') or \
           t.group(2).startswith ('Freeing unused kernel memory'):
            kernel.duration = time_ms / 10
            continue

#               print "foo: '%s' '%s' '%s'" % (type, func, rest)
        if type == "calling":
            ppid = kernel.pid
            p = re.match ("\@ (\d+)", rest)
            if p is not None:
                ppid = float (p.group(1)) / 1000
#                               print "match: '%s' ('%g') at '%s'" % (func, ppid, time_ms)
            name = func.split ('+', 1) [0]
            idx += inc
            processMap[func] = Process(writer, ppid + idx, name, ppid, time_ms / 10)
        elif type == "initcall":
#                       print "finished: '%s' at '%s'" % (func, time_ms)
            if func in processMap:
                process = processMap[func]
                process.duration = (time_ms / 10) - process.start_time
            else:
                print("corrupted init call for %s" % (func))

        elif type == "async_waiting" or type == "async_continuing":
            continue # ignore

    return processMap.values()

def _parse_events_log(writer, tf, file):
    '''
    Parse a generic log format produced by target-specific filters.
    Extracting the standard fields from the target-specific raw_file
    is the responsibility of target-specific pre-processors.
    Eventual output is per-process lists of events in temporal order.
    '''
    def _readline(raw_log_filename, raw_log_seek):
        file = tf.extractfile(raw_log_filename)
        if not file:
            return
        file.seek(raw_log_seek)
        line = file.readline()
        file.close()
        return line

    split_re = re.compile ("^(\S+) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+) +(\S+)$")
    timed_blocks = _parse_timed_blocks(file)
    samples = []
    for time, lines in timed_blocks:
        for line in lines:
            if line is '':
                continue
            m = split_re.match(line)
            if m == None or m.lastindex < 7:    # XX  Ignore bad data from Java events, for now
                continue
            time_usec = long(m.group(1))
            pid = int(m.group(2))
            tid = int(m.group(3))
            comm = m.group(4)
            func_file_line = m.group(5)
            raw_log_filename = m.group(6)
            raw_log_seek = int(m.group(7))
            raw_log_line = _readline(raw_log_filename, raw_log_seek)
            samples.append( EventSample(time, time_usec, pid, tid, comm, func_file_line, raw_log_line))
    return samples

#
# Parse binary pacct accounting file output if we have one
# cf. /usr/include/linux/acct.h
#
def _parse_pacct(writer, file):
    # read LE int32
    def _read_le_int32(file):
        byts = file.read(4)
        return (ord(byts[0]))       | (ord(byts[1]) << 8) | \
               (ord(byts[2]) << 16) | (ord(byts[3]) << 24)

    parent_map = {}
    parent_map[0] = 0
    while file.read(1) != "": # ignore flags
        ver = file.read(1)
        if ord(ver) < 3:
            print("Invalid version 0x%x" % (ord(ver)))
            return None

        file.seek (14, 1)     # user, group etc.
        pid = _read_le_int32 (file)
        ppid = _read_le_int32 (file)
#               print "Parent of %d is %d" % (pid, ppid)
        parent_map[pid] = ppid
        file.seek (4 + 4 + 16, 1) # timings
        file.seek (16, 1)         # acct_comm
    return parent_map

def _parse_paternity_log(writer, file):
    parent_map = {}
    parent_map[0] = 0
    for line in file.read().split('\n'):
        elems = line.split(' ') # <Child> <Parent>
        if len (elems) >= 2:
#                       print "paternity of %d is %d" % (int(elems[0]), int(elems[1]))
            parent_map[int(elems[0])] = int(elems[1])
        elif line is not '':
            print("Odd paternity line '%s'" % (line))
    return parent_map

def _parse_cmdline_log(writer, file):
    cmdLines = {}
    for block in file.read().split('\n\n'):
        lines = block.split('\n')
        if len (lines) >= 3:
#                       print "Lines '%s'" % (lines[0])
            pid = int (lines[0])
            values = {}
            values['exe'] = lines[1].lstrip(':')
            args = lines[2].lstrip(':').split('\0')
            args.pop()
            values['args'] = args
            cmdLines[pid] = values
    return cmdLines

def get_num_cpus(headers):
    """Get the number of CPUs from the system.cpu header property. As the
    CPU utilization graphs are relative, the number of CPUs currently makes
    no difference."""
    if headers is None:
        return 1
    if headers.get("system.cpu.num"):
        return max (int (headers.get("system.cpu.num")), 1)
    cpu_model = headers.get("system.cpu")
    if cpu_model is None:
        return 1
    mat = re.match(".*\\((\\d+)\\)", cpu_model)
    if mat is None:
        return 1
    return max (int(mat.group(1)), 1)

def _do_parse(writer, state, tf, name, file, options):
    writer.status("parsing '%s'" % name)
    t1 = clock()
    if name == "header":
        state.headers = _parse_headers(file)
    elif name == "proc_diskstats.log":
        state.disk_stats = _parse_proc_disk_stat_log(file, options, get_num_cpus(state.headers))
    elif name == "taskstats.log":
        state.ps_stats = _parse_taskstats_log(writer, file)
        state.taskstats = True
    elif name == "proc_stat.log":
        state.cpu_stats = _parse_proc_stat_log(file)
    elif name == "proc_meminfo.log":
        state.mem_stats = _parse_proc_meminfo_log(file)
    elif name == "dmesg":
        state.kernel = _parse_dmesg(writer, file)
    elif name == "cmdline2.log":
        state.cmdline = _parse_cmdline_log(writer, file)
    elif name == "paternity.log":
        state.parent_map = _parse_paternity_log(writer, file)
    elif name == "proc_ps.log":  # obsoleted by TASKSTATS
        state.ps_stats = _parse_proc_ps_log(options, writer, file)
    elif name == "proc_ps_threads.log":
        state.ps_stats = _parse_proc_ps_threads_log(options, writer, file)
    elif name == "kernel_pacct": # obsoleted by PROC_EVENTS
        state.parent_map = _parse_pacct(writer, file)
    elif name == "events-7.log":   # 7 is number of fields -- a crude versioning scheme
        state.events = _parse_events_log(writer, tf, file)
    t2 = clock()
    writer.info("  %s seconds" % str(t2-t1))
    return state

def parse_file(writer, state, filename, options):
    if state.filename is None:
        state.filename = filename
    basename = os.path.basename(filename)
    with open(filename, "rb") as file:
        return _do_parse(writer, state, None, basename, file, options)

def parse_paths(writer, state, paths, options):
    for path in paths:
        root, extension = os.path.splitext(path)
        if not(os.path.exists(path)):
            raise ParseError("\n\tpath '%s' does not exist" % path)
        state.filename = path
        if os.path.isdir(path):
            files = [ f for f in [os.path.join(path, f) for f in os.listdir(path)] if os.path.isfile(f) ]
            files.sort()
            state = parse_paths(writer, state, files, options)
        elif extension in [".tar", ".tgz", ".gz"]:
            if extension == ".gz":
                root, extension = os.path.splitext(root)
                if extension != ".tar":
                    writer.warn("warning: can only handle zipped tar files, not zipped '%s'-files; ignoring" % extension)
                    continue
            tf = None
            try:
                writer.status("parsing '%s'" % path)
                tf = tarfile.open(path, 'r:*')
                for name in tf.getnames():
                    state = _do_parse(writer, state, tf, name, tf.extractfile(name), options)
            except tarfile.ReadError as error:
                raise ParseError("error: could not read tarfile '%s': %s." % (path, error))
            finally:
                if tf != None:
                    tf.close()
        else:
            state = parse_file(writer, state, path, options)
    return state
