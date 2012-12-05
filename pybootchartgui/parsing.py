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
import struct
import bisect
from time import clock
import collections
from collections import defaultdict
from functools import reduce
from types import *

from .draw import usec_to_csec, csec_to_usec
from .samples import *
from .process_tree import ProcessTree
from . import writer

# Parsing produces as its end result a 'Trace'

class Trace:
    def __init__(self, options):
        self.headers = None
        self.disk_stats = None
        self.ps_stats = None
        self.ps_threads_stats = None
        self.taskstats = None
        self.cpu_stats = None   # from /proc/stat
        self.cmdline = None
        self.kernel = None
        self.kernel_tree = None
        self.filename = None
        self.parent_map = None
        self.mem_stats = None

        # Read in all files, parse each into a time-ordered list, init many of the attributes above
        parse_paths (self, options.paths, options)

        # FIXME: support deprecated data sets that contain no proc_ps.log, only proc_ps_threads.log
        if not self.ps_stats:
            self.ps_stats = self.ps_threads_stats
        elif self.ps_threads_stats:
            for (k,v) in self.ps_threads_stats.process_map.iteritems():
                self.ps_stats.process_map[k] = v
            self.ps_threads_stats = True

        if not self.valid():
            raise ParseError("empty state: '%s' does not contain a valid bootchart" % ", ".join(paths))

        # Turn that parsed information into something more useful
        # link processes into a tree of pointers, calculate statistics
        self.adorn_process_map(options)

        # Crop the chart to the end of the first idle period after the given
        # process
        if options.crop_after:
            idle = self.crop (options.crop_after)
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

        self.proc_tree = ProcessTree(self.kernel, self.ps_stats,
                                     self.ps_stats.sample_period,
                                     self.headers.get("profile.process"),
                                     options, idle, self.taskstats,
                                     self.parent_map is not None)

        if self.kernel is not None:
            self.kernel_tree = ProcessTree(self.kernel, None, 0,
                                           self.headers.get("profile.process"),
                                           options, None, None, True)

        self._generate_sample_start_pseudo_events(options)

    def _generate_sample_start_pseudo_events(self, options):
        es = EventSource(" ~ bootchartd sample start points", "", "")   # empty regex
        es.parsed = []
        es.enable = False
        init_pid = 1
        for cpu in self.cpu_stats:
            # assign to the init process's bar, for lack of any better
            ev = EventSample(csec_to_usec(cpu.time),
                             init_pid, init_pid,
                             "comm", None, None, "")
            es.parsed.append(ev)
        options.event_source[es.label] = es

    def valid(self):
        return self.headers != None and self.disk_stats != None and \
               self.ps_stats != None and self.cpu_stats != None

    def adorn_process_map(self, options):

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

        # re-parent any stray orphans if we can
        if self.parent_map is not None:   # requires either "kernel_pacct" or "paternity.log"
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

    def crop(self, crop_after):

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

        self.end_time = crop_at

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

def _save_PC_sample(trace, es, time, pid, tid, comm, addr):
    ev = EventSample(csec_to_usec(time), pid, tid, comm, None, None, "0x{0:08x}".format(addr))
    es.parsed.append(ev)

# Cases to handle:
#   1. run starting   (ltime==None)
#   1.1  thread started in preceding sample_period
#   1.2  thread started earlier
#   2. run continuing
#   2.1  thread continues    (tid in processMap)
#   2.2  thread starts
def _handle_sample(options, trace, processMap, ltime, time,
                   pid, tid, lwp, cmd, state, ppid, userCpu, sysCpu,
                   kstkeip, wchan, delayacct_blkio_ticks, c_user, c_sys, starttime,
                   num_cpus):
    assert(type(c_user) is IntType)
    assert(type(c_sys) is IntType)

    if tid in processMap:
        proc = processMap[tid]
        proc.set_cmd(cmd)
    else:
        if time < starttime:
            # large values signify a collector problem, e.g. resource starvation
            writer.info("time (%dcs) < starttime (%dcs), diff %d -- TID %d" %
                          (time, starttime, time-starttime, tid/1000))

        proc = Process(pid, tid, lwp, cmd, ppid, starttime)
        if ltime:      # process is starting during profiling run
            proc.user_cpu_ticks[0] = 0
            proc.sys_cpu_ticks [0] = 0
            proc.delayacct_blkio_ticks [0] = 0
            ltime = starttime
        else:
            proc.user_cpu_ticks[0] = userCpu
            proc.sys_cpu_ticks [0] = sysCpu
            proc.delayacct_blkio_ticks [0] = delayacct_blkio_ticks
            ltime = -100000   #  XX  hacky way of forcing reported load toward zero
        proc.user_cpu_ticks[-1] =        proc.user_cpu_ticks[0]
        proc.sys_cpu_ticks [-1] =        proc.sys_cpu_ticks [0]
        proc.delayacct_blkio_ticks[-1] = proc.delayacct_blkio_ticks[0]
        processMap[tid] = proc      # insert new process into the dict

    userCpuLoad, sysCpuLoad, delayacctBlkioLoad = proc.calc_load(userCpu, sysCpu, delayacct_blkio_ticks,
                                                                    max(1, time - ltime), num_cpus)

    cpuSample = ProcessCPUSample('null', userCpuLoad, sysCpuLoad, c_user, c_sys, delayacctBlkioLoad, 0.0)
    proc.samples.append(ProcessSample(time, state, cpuSample))

    # per-tid store for use by a later phase of parsing of samples gathered at this 'time'
    proc.user_cpu_ticks[-1] = userCpu
    proc.sys_cpu_ticks[-1] = sysCpu
    proc.delayacct_blkio_ticks[-1] = delayacct_blkio_ticks

    if state == "R" and kstkeip != 0 and kstkeip != 0xffffffff:
            _save_PC_sample(trace, options.event_source[" ~ current PC, if thread Runnable"],
                            time, pid/1000, tid/1000, cmd, kstkeip)
    if state == "D" and kstkeip != 0 and kstkeip != 0xffffffff:
            _save_PC_sample(trace, options.event_source[" ~ current PC, if thread in non-interruptible D-wait"],
                            time, pid/1000, tid/1000, cmd, kstkeip)
    if state == "D" and wchan != 0:
        _save_PC_sample(trace, options.event_source[" ~ kernel function wchan, if thread in non-interruptible D-wait"],
                        time, pid/1000, tid/1000, cmd, wchan)
    return processMap

# Consider this case: a process P and three waited-for children C1, C2, C3.
# The collector daemon bootchartd takes samples at times t-2 and t-1.
#
#                             t-2   t-2+e   t-1-e     t-1    -->
#                               .       .       .       .
#    bootchartd            sample       .       .  sample
#                               .       .       .       .
#    P                          R       R       R       R
#    C1 -- long-lived           R       R       R       R
#    C2 -- exited               R    exit       -       -
#    C3 -- phantom              -    fork    exit       -
#
# C1's CPU usage will be reported at both sample times t-2 and t-1 in the
# {utime,stime} field of /proc/PID/stat, in units of clock ticks.
# C2's usage will be reported at t-2.  Any whole clock ticks thereafter will be
# accumulated by the kernel, and reported to bootchartd at t-1 in the
# {cutime,cstime} fields of its parent P, along with the rest of the clock ticks
# charged to C2 during its entire lifetime.
# C3's clock ticks will never be seen directly in any sample taken by
# bootchartd, rather only in increments to P's {cutime,cstime} fields as
# reported at t-1.
#
# We wish to graph on P's process bar at time t-1 all clock ticks consumed by
# any of its children between t-2 and t-1 that cannot be reported on the
# children's process bars -- C2's process bar ends at t-2 and C3 has none at
# all.  We'll call it "lost child time".  The lost clock ticks may be counted
# so:
#
#     P{cutime,cstime}(t-1) - P{cutime,cstime}(t-2) - C2{utime,stime}(t-2)

def accumulate_missing_child_ltime(processMap, ltime):
    """ For only whole-process children found to have gone missing between 'ltime' and 'time' i.e. now,
    accumulate clock ticks of each child's lifetime total to a counter
    in the parent's Process"""
    for p_p in processMap.itervalues():
        p_p.missing_child_ticks = 0

    for c_p in processMap.itervalues():
        if c_p.ppid != 0 and \
               c_p.tid == c_p.pid and \
               c_p.samples[-1].time == ltime:     # must have exited at 'time'
            p_p = processMap[c_p.ppid]
            p_p.missing_child_ticks += c_p.user_cpu_ticks[1] + c_p.sys_cpu_ticks[1]
            continue
            print "gone_missing,_last_seen_at", ltime, \
                  c_p.ppid/1000, ":", c_p.pid/1000, ":", c_p.tid/1000, p_p.missing_child_ticks

def compute_lost_child_times(processMap, ltime, time):
    """ For each parent process live at 'time', find clock ticks reported by
    children exiting between 'ltime' and 'time'.
    calculate CPU consumption during
    the sample period of newly-lost children.
    Insert time-weighted value into current sample."""
    interval = time - ltime
    for p_p in processMap.itervalues():
        if p_p.pid != p_p.tid or \
               p_p.samples[-1].time != time or \
               len(p_p.samples) < 2:
            continue
        def total_c_ticks(sample):
            return sample.cpu_sample.c_user + sample.cpu_sample.c_sys
        parent_c_tick_delta = total_c_ticks(p_p.samples[-1]) \
                              - total_c_ticks(p_p.samples[-2])
        # See this line in the diagram and comment above.
        #     P{cutime,cstime}(t-1) - P{cutime,cstime}(t-2) - C2{utime,stime}(t-2)
        # XX  Aggregating user and sys at this phase, before stuffing result into a per-sample
        # object.  Some other time might be better.
        lost_child_ticks = parent_c_tick_delta - p_p.missing_child_ticks

        p_p.samples[-1].lost_child = float(lost_child_ticks)/interval
        if (parent_c_tick_delta != 0 or p_p.missing_child_ticks != 0):
            print "compute_lost_child_times()", time, p_p.pid/1000, \
                  parent_c_tick_delta, p_p.missing_child_ticks, lost_child_ticks, interval #, p_p.samples[-1].lost_child

def _distribute_belatedly_reported_delayacct_blkio_ticks(processMap):
    for p in processMap.itervalues():
        io_acc = 0.0
        for s in p.samples[-1:0:-1]:
            s.cpu_sample.io += io_acc
            io_acc = 0.0
            if s.cpu_sample.io + s.cpu_sample.user + s.cpu_sample.sys > 1.0:
                io_acc = s.cpu_sample.io + s.cpu_sample.user + s.cpu_sample.sys - 1.0
                s.cpu_sample.io -= io_acc

def _init_pseudo_EventSources_for_PC_samples(options):
    for label, enable in [
        (" ~ current PC, if thread Runnable", False),
        (" ~ current PC, if thread in non-interruptible D-wait", False),
        (" ~ kernel function wchan, if thread in non-interruptible D-wait", True)]:
        es = EventSource(label, "", "")   # empty regex
        es.enable = enable
        es.parsed = []
        options.event_source[label] = es   # XX  options.event_source must be used because the Trace object is not yet instantiated

def _parse_proc_ps_log(options, trace, file, num_cpus):
    """
     * See proc(5) for details.
     *
     * {pid, comm, state, ppid, pgrp, session, tty_nr, tpgid, flags, minflt, cminflt, majflt, cmajflt, utime, stime,
     *  cutime, cstime, priority, nice, 0, itrealvalue, starttime, vsize, rss, rlim, startcode, endcode, startstack,
     *  kstkesp, kstkeip}
    """
    _init_pseudo_EventSources_for_PC_samples(options)

    processMap = {}
    ltime = None
    timed_blocks = _parse_timed_blocks(file)
    for time, lines in timed_blocks:
        for line in lines:
            if line is '': continue
            tokens = line.split(' ')
            if len(tokens) < 21:
                continue

            offset = [index for index, token in enumerate(tokens[1:]) if token[-1] == ')'][0]
            pid, cmd, state, ppid = int(tokens[0]), ' '.join(tokens[1:2+offset]), tokens[2+offset], int(tokens[3+offset])
            userCpu, sysCpu = int(tokens[13+offset]), int(tokens[14+offset]),
            c_user, c_sys = int(tokens[15+offset]), int(tokens[16+offset])
            starttime = int(tokens[21+offset])
            kstkeip = int(tokens[29+offset])
            wchan = int(tokens[34+offset])
            delayacct_blkio_ticks = int(tokens[41+offset])

            # magic fixed point-ness ...
            pid *= 1000
            ppid *= 1000
            processMap = _handle_sample(options, trace, processMap, ltime, time,
                                        pid, pid, False, cmd, state, ppid,
                                        userCpu, sysCpu, kstkeip, wchan, delayacct_blkio_ticks, c_user, c_sys, starttime,
                                        num_cpus)
        if ltime:
            accumulate_missing_child_ltime(processMap, ltime)
            # compute_lost_child_times(processMap, ltime, time)
        ltime = time

    if len (timed_blocks) < 2:
        return None

    startTime = timed_blocks[0][0]
    avgSampleLength = (ltime - startTime)/(len (timed_blocks) - 1)

    _distribute_belatedly_reported_delayacct_blkio_ticks(processMap)

    return ProcessStats (processMap, len (timed_blocks), avgSampleLength)

def _parse_proc_ps_threads_log(options, trace, file):
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
     *   17* delayacct_blkio_ticks -- in proc_ps_threads-2.log only, requires CONFIG_TASK_DELAY_ACCT
    """
    _init_pseudo_EventSources_for_PC_samples(options)

    processMap = {}
    ltime = None
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
            userCpu, sysCpu = int(tokens[7+offset]), int(tokens[8+offset])
            c_user, c_sys = int(tokens[9+offset]), int(tokens[10+offset])
            kstkeip = int(tokens[14+offset])
            wchan = int(tokens[15+offset])
            delayacct_blkio_ticks = int(tokens[17+offset]) if len(tokens) == 18+offset else 0

            assert(type(c_user) is IntType)
            assert(type(c_sys) is IntType)
            starttime = int(tokens[13+offset])

            # force sorting later than whole-process records from proc_ps.log
            pid = pid * PID_SCALE + LWP_OFFSET
            tid = tid * PID_SCALE + LWP_OFFSET
            ppid *= 1000

            processMap = _handle_sample(options, trace, processMap, ltime, time,
                                        pid, tid, True, cmd, state, ppid,
                                        userCpu, sysCpu, kstkeip, wchan, delayacct_blkio_ticks, c_user, c_sys, starttime,
                                        1)
        ltime = time

    if len (timed_blocks) < 2:
        return None

    startTime = timed_blocks[0][0]
    avgSampleLength = (ltime - startTime)/(len (timed_blocks) - 1)

    _distribute_belatedly_reported_delayacct_blkio_ticks(processMap)

    return ProcessStats (processMap, len (timed_blocks), avgSampleLength)

def _parse_taskstats_log(file):
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
            process = Process(1, '[init]', False, 0, 0)
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
                    process = process.split (pid, cmd, ppid, time)
                    processMap[pid] = process
                else:
                    process.cmd = cmd;
            else:
                process = Process(pid, pid, False, cmd, ppid, time)
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
                                      0, 0,
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

    return ProcessStats (processMap, len (timed_blocks), avgSampleLength)

def get_num_cpus(file):
    """Get the number of CPUs from the ps_stats file."""
    num_cpus = -1
    for time, lines in _parse_timed_blocks(file):
        for l in lines:
            if l.split(' ')[0] == "intr":
                file.seek(0)
                return num_cpus
            num_cpus += 1
    assert(False)

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

# matched not against whole line, but field only
#  XX  Rework to be not a whitelist but rather a blacklist of uninteresting devices e.g. "loop*"
part_name_re = re.compile('^([hsv]d.|mtdblock\d|mmcblk\d.*|cciss/c\d+d\d+.*)$')

def _parse_proc_disk_stat_log(file, options, numCpu):
    """
    Input file is organized:
        [(time, [(major, minor, partition_name, iostats[])])]
    Output form, as required for drawing:
        [(partition_name, [(time, iostat_deltas[])])]

    Finally, produce pseudo-partition sample sets containing sums
    over each physical storage device, e.g. sda, mmcblk0.

    The input file was generated by block/genhd.c .
    """

    strip_slash_dev_slash = re.compile("/dev/(.*)$")
#    this_partition_regex_re = re.compile('^' + part + '.*$')

    parts_dict = {}
    # for every timed_block, collect per-part lists of samples in 'parts_dict'
    for time, lines in _parse_timed_blocks(file):
        for line in lines:
            def line_to_tokens(line):
                linetokens = line.split()
                return linetokens if len(linetokens) == 14 else None

            tokenized_partition = line_to_tokens(line)
            if not tokenized_partition:
                continue
            sample = PartitionSample( time, IOStat_make(tokenized_partition))
            if not part_name_re.match(sample.iostat.name):
                continue
            if not sample.iostat.name in parts_dict:
                parts_dict[sample.iostat.name] = []
            parts_dict[sample.iostat.name].append(sample)

    # take deltas, discard original (cumulative) samples
    partitions = []
    WHOLE_DEV = 0
    for partSamples in parts_dict.iteritems():
        partitions.append( PartitionDeltas(
            partSamples[1], numCpu,
            partSamples[0],
            partSamples[0]  # possibly to be replaced with partition_labels from command line
            ))
    partitions.sort(key = lambda p: p.name)
    partitions[WHOLE_DEV].hide = False   # whole device

    if len(options.partitions) > 0:
        for opt_name in options.partitions:
            for part in partitions:
                if part.name == opt_name:
                    part.hide = False
                    part.label = options.partition_labels[0]
                    options.partition_labels = options.partition_labels[1:]

    return partitions

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
def _parse_dmesg(file):
    timestamp_re = re.compile ("^\[\s*(\d+\.\d+)\s*]\s+(.*)$")
    split_re = re.compile ("^(\S+)\s+([\S\+_-]+) (.*)$")
    processMap = {}
    idx = 0
    inc = 1.0 / 1000000
    kernel = Process(idx, idx, False, "k-boot", 0, 0.1)
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
            processMap[func] = Process(ppid + idx, ppid + idx, False, name, ppid, time_ms / 10)
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

def get_boot_relative_usec(state, boot_time_as_usecs_since_epoch, time_usec):
    boot_relative_usec = time_usec - boot_time_as_usecs_since_epoch
    if boot_relative_usec < csec_to_usec(state.start_time):
        return None
    if boot_relative_usec > csec_to_usec(state.end_time):
        return None
    return boot_relative_usec

def parse_raw_log(state, boot_time_as_usecs_since_epoch, log_file, fields_re):
    '''
    Parse variously-formatted logs containing recorded events, as guided by a
    set of target-specific regexps provided on the command line.
    Eventual output is per-process lists of events in temporal order.
    '''
    fields_re_c = re.compile(fields_re)

    samples = []
    for line in log_file:
            if line is '':
                continue
            m = fields_re_c.search(line)
            if m == None:
                continue

            time_usec = float(m.group('CLOCK_REALTIME_usec'))  # See `man 3 clock_gettime`
            # tolerate any loss of precision in the timestamp, by rounding down
            # FIXME: Don't simply round down -- show the user the (min,max) interval
            # corresponding to the low-precision number.
            while time_usec < 1300*1000*1000*1000*1000:
                time_usec *= 10.0
            while time_usec > 1300*1000*1000*1000*1000 * 2:
                time_usec /= 10.0

            try:
                pid = int(m.group('pid'))
            except IndexError:
                # "inherited" by parent's per-thread/process bar
                pid = 1

            try:
                tid = int(m.group('tid'))
            except IndexError:
                # "inherited" by parent's per-thread/process bar
                tid = pid

            try:
                comm = m.group('comm')
            except IndexError:
                comm = ""

            raw_log_seek = log_file.tell()

            boot_relative_usec = get_boot_relative_usec(
                state, boot_time_as_usecs_since_epoch, time_usec)
            if boot_relative_usec:
                samples.append( EventSample(
                    boot_relative_usec,
                    pid, tid, comm,
                    log_file, raw_log_seek, line))
    return samples

#
# Parse binary pacct accounting file output if we have one
# cf. /usr/include/linux/acct.h
#
def _parse_pacct(file):
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

def _parse_paternity_log(file):
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

def _parse_cmdline_log(file):
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

def _do_parse(state, tf, name, file, options):
    writer.status("parsing '%s'" % name)
    t1 = clock()
    if name == "header":
        state.headers = _parse_headers(file)
    elif name == "proc_diskstats.log":
        state.disk_stats = _parse_proc_disk_stat_log(file, options, state.num_cpus)
    elif name == "taskstats.log":
        state.ps_stats = _parse_taskstats_log(file)
        state.taskstats = True
    elif name == "proc_stat.log":
        state.num_cpus = get_num_cpus(file)
        state.cpu_stats = _parse_proc_stat_log(file)
        state.start_time = state.cpu_stats[0].time
        state.end_time = state.cpu_stats[-1].time
    elif name == "proc_meminfo.log":
        state.mem_stats = _parse_proc_meminfo_log(file)
    elif name == "dmesg":
        state.kernel = _parse_dmesg(file)
    elif name == "cmdline2.log":
        state.cmdline = _parse_cmdline_log(file)
    elif name == "paternity.log":
        state.parent_map = _parse_paternity_log(file)
    elif name == "proc_ps.log":  # obsoleted by TASKSTATS
        state.ps_stats = _parse_proc_ps_log(options, state, file, state.num_cpus)
    elif name == "proc_ps_threads.log" or  name == "proc_ps_threads-2.log" :
        state.ps_threads_stats = _parse_proc_ps_threads_log(options, state, file)
    elif name == "kernel_pacct": # obsoleted by PROC_EVENTS
        state.parent_map = _parse_pacct(file)
    elif hasattr(options, "event_source"):
        boot_t = state.headers.get("boot_time_as_usecs_since_epoch")
        assert boot_t, NotImplementedError
        for es in options.event_source.itervalues():
            if name == es.filename:
                parser = parse_raw_log
                es.parsed = parser(state, long(boot_t), file, es.regex)
                es.enable = len(es.parsed) > 0
                file.seek(0)   # file will be re-scanned for each regex
                writer.info("parsed {0:5d} events from {1:16s} using {2:s}".format(
                        len(es.parsed), file.name, es.regex))
    else:
        pass # unknown file in tarball
    t2 = clock()
    writer.info("  %s seconds" % str(t2-t1))
    return state

def parse_file(state, filename, options):
    if state.filename is None:
        state.filename = filename
    basename = os.path.basename(filename)
    with open(filename, "rb") as file:
        return _do_parse(state, None, basename, file, options)

def parse_paths(state, paths, options):
    for path in paths:
        root, extension = os.path.splitext(path)
        if not(os.path.exists(path)):
            raise ParseError("\n\tpath '%s' does not exist" % path)
        state.filename = path
        if os.path.isdir(path):
            files = [ f for f in [os.path.join(path, f) for f in os.listdir(path)] if os.path.isfile(f) ]
            files.sort()
            state = parse_paths(state, files, options)
        elif extension in [".tar", ".tgz", ".gz"]:
            if extension == ".gz":
                root, extension = os.path.splitext(root)
                if extension != ".tar":
                    writer.warn("warning: can only handle zipped tar files, not zipped '%s'-files; ignoring" % extension)
                    continue
            state.tf = None
            try:
                state.tf = tarfile.open(path, 'r:*')

                # parsing of other files depends on these
                early_opens = ["header", "proc_stat.log"]
                def not_in_early_opens(name):
                    return len(filter(lambda n: n==name, early_opens)) == 0

                for name in early_opens + filter(not_in_early_opens, state.tf.getnames()):
                    # Extracted file should be seekable, presumably a decompressed copy.
                    #   file:///usr/share/doc/python2.6/html/library/tarfile.html?highlight=extractfile#tarfile.TarFile.extractfile
                    # XX  Python 2.6 extractfile() assumes file contains lines of text, not binary :-(
                    extracted_file = state.tf.extractfile(name)
                    if not extracted_file:
                        continue
                    state = _do_parse(state, state.tf, name, extracted_file, options)
            except tarfile.ReadError as error:
                raise ParseError("error: could not read tarfile '%s': %s." % (path, error))
        else:
            state = parse_file(state, path, options)

        for es in options.event_source.itervalues():
            if es.parsed == None:
                raise ParseError("\n\tevents file found on command line but not in tarball: {0}\n".format(es.filename))
    return state
