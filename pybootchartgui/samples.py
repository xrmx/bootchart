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

from types import *
import collections
import re

from . import writer

# To understand this, see comment "Fedora hack"
PID_SCALE = 1000
LWP_OFFSET = 1

KTHREADD_PID = 2

class EventSource:
    """ Extract (EventSample)s from some disjoint subset of the available log entries """
    def __init__(self, label, filename, regex):
        self.label = label    # descriptive name for GUI
        self.filename = filename
        self.regex = regex
        self.parsed = None  # list of EventSamples parsed from filename
        self.enable = None  # initially set to True iff at least one sample was parsed; maintained by gui.py thereafter

class EventSample:
    def dump_format(self):
        return "{0:10f} {1:5d} {2:5d} {3} {4}".format( \
            float(self.time_usec)/1000/1000, self.pid, self.tid, self.comm, self.raw_log_line.rstrip())

    def __init__(self, time_usec, pid, tid, comm, raw_log_file, raw_log_seek, raw_log_line):
        self.time_usec = time_usec
        self.pid = pid
        self.tid = tid
        self.comm = comm
        self.raw_log_file = raw_log_file
        self.raw_log_seek = raw_log_seek
        self.raw_log_line = raw_log_line
        if pid != 1:
            writer.debug(self.dump_format())

class EventColor:
    def __init__(self, label, regex0, regex1, enable):
        self.label = label
        self.color_regex = []
        self.color_regex.append(re.compile(regex0))
        if regex1 is not None:
            self.color_regex.append(re.compile(regex1))
        self.enable = enable

#  See Documentation/iostats.txt.
IOStat_field_names = ['major', 'minor', 'name',
                      'nreads',  'nreads_merged',  'nsectors_read',  'nread_time_msec',
                      'nwrites', 'nwrites_merged', 'nsectors_write', 'nwrite_time_msec',
                      'nio_in_progress',                                 # not an accumulator
                      'io_msec', 'io_weighted_msec']
IOStat = collections.namedtuple('typename_IOStat', IOStat_field_names)

# wrapper necessary to produce desired 'int' rather than 'string' types
def IOStat_make(fields_as_list):
    return IOStat._make(fields_as_list[:3] + [int(a) for a in fields_as_list[3:]])

def IOStat_op(sa, sb, f):
    la = list(sa.iostat)
    lb = list(sb.iostat)
    preamble = [sa.iostat.major, sa.iostat.minor, sa.iostat.name]
    return IOStat._make(preamble +
                        [f(int(a),int(b)) for a, b in zip(la[3:], lb[3:])])

def IOStat_diff(sa, sb):
    return IOStat_op(sa, sb, lambda a,b: a - b)
def IOStat_sum(sa, sb):
    return IOStat_op(sa, sb, lambda a,b: a + b)
def IOStat_max2(sa, sb):
    return IOStat_op(sa, sb, lambda a,b: max(a, b))

class PartitionSample:
    def __init__(self, time, IOStat):
        self.time = time
        self.iostat = IOStat

class PartitionDelta:
    def __init__(self, time, IOStat, util, nio_in_progress):
        self.util = util                              # computed, not a simple delta
        self.nio_in_progress = int(nio_in_progress)   # an instantaneous count, not a delta
        self.s = PartitionSample(time, IOStat)

class PartitionDeltas:
    def __init__(self, partSamples, numCpu, name, label):
        assert( type(partSamples) is list)

        self.name = name
        self.label = label      # to be drawn for this PartitionSamples object, in a label on the chart
        self.numCpu = numCpu
        self.hide = True
        self.part_deltas = []

        COALESCE_THRESHOLD = 1 # XX needs synchronization with other graphs
        partSamples_coalesced = [(partSamples[0])]
        for sample in partSamples:
            if sample.time - partSamples_coalesced[-1].time < COALESCE_THRESHOLD:
                continue
            partSamples_coalesced.append(sample)

        for sample1, sample2 in zip(partSamples_coalesced[:-1], partSamples_coalesced[1:]):
            interval = sample2.time - sample1.time
            diff = IOStat_diff(sample2, sample1)
            util = float(diff.io_msec) / 10 / interval / numCpu
            self.part_deltas.append( PartitionDelta(sample2.time, diff,
                                                    util, sample2.iostat.nio_in_progress))

        # Very short intervals amplify round-off under division by time delta, so coalesce now.
        # XX  scaling issue for high-efficiency collector!

class SystemCPUSample:
    def __init__(self, time, user, sys, io, procs_running, procs_blocked):
        self.time = time
        self.user = user
        self.sys = sys
        self.io = io
        self.procs_running = procs_running
        self.procs_blocked = procs_blocked

class ProcessCPUSample:
    def __init__(self, time, user, sys, c_user, c_sys, io, swap):
        self.time = time
        self.user = user
        self.sys = sys
        self.c_user = c_user  # directly from /proc: accumulates upon exit of waited-for child
        self.c_sys = c_sys
        self.io = io        # taskstats-specific
        self.swap = swap    # taskstats-specific

        assert(type(self.c_user) is IntType)
        assert(type(self.c_sys) is IntType)

    @property
    def cpu(self):
        return self.user + self.sys

    def __str__(self):
        return str(self.time) + "\t" + str(self.user) + "\t" + \
               str(self.sys) + "\t" + str(self.io) + "\t" + str (self.swap)

class ProcessSample:
    def __init__(self, time, state, cpu_sample):
        self.time = time
        self.state = state
        self.cpu_sample = cpu_sample  # ProcessCPUSample

        # delta per sample interval. Computed later in parsing.
        self.lost_child = None

    def __str__(self):
        return str(self.time) + "\t" + str(self.state) + "\t" + str(self.cpu_sample)

class MemSample:
    def __init__(self, time):
        self.time = time
        self.records = {}

    def add_value(self, name, value):
        self.records[name] = value


class ProcessStats:
    """stats over the collection of all processes, all samples"""
    def __init__(self, process_map, sample_count, sample_period):
        self.process_map = process_map
        self.sample_count = sample_count
        self.sample_period = sample_period
        writer.info ("%d samples, avg. sample length %f" % (self.sample_count, self.sample_period))
        writer.info ("process list size: %d" % len (self.process_map.values()))

class Process:
    def __init__(self, pid, tid, lwp, cmd, ppid, start_time):
        self.pid = pid
        self.tid = tid
        assert(type(lwp) is BooleanType)
        self.lwp_list = None if lwp else []
        self.exe = cmd  # may be overwritten, later
        self.args = []
        self.ppid = ppid
        self.set_cmd(cmd)  # XX  depends on self.ppid
        self.start_time = start_time
        self.duration = 0
        self.samples = []        # list of ProcessCPUSample
        self.events = []         # time-ordered list of EventSample
        self.event_interval_0_tx = None
        self.parent = None
        self.child_list = []

        self.user_cpu_ticks = [None, 0]    # [first, last]
        self.sys_cpu_ticks = [None, 0]
        self.delayacct_blkio_ticks = [None, 0]

        # For transient use as an accumulator during early parsing -- when
        # concurrent samples of all threads can be accessed O(1).
        self.missing_child_ticks = None

        self.last_cpu_ns = 0
        self.last_blkio_delay_ns = 0
        self.last_swapin_delay_ns = 0

        # dynamic, view-dependent per-process state boolean
        self.draw = True

    # Is this an LWP a/k/a pthread?
    def lwp(self):
        return self.lwp_list == None

    def cpu_tick_count_during_run(self):
        ''' total CPU clock ticks reported for this process during the profiling run'''
        return self.user_cpu_ticks[-1] + self.sys_cpu_ticks[-1] \
                        - (self.user_cpu_ticks[0] + self.sys_cpu_ticks[0])

    # split this process' run - triggered by a name change
    #  XX  called only if taskstats.log is provided (bootchart2 daemon)
    def split(self, pid, cmd, ppid, start_time):
        split = Process (pid, cmd, ppid, start_time)

        split.last_cpu_ns = self.last_cpu_ns
        split.last_blkio_delay_ns = self.last_blkio_delay_ns
        split.last_swapin_delay_ns = self.last_swapin_delay_ns

        return split

    def __str__(self):
        return " ".join([str(self.pid), self.cmd, str(self.ppid), '[ ' + str(len(self.samples)) + ' samples ]' ])

    def calc_stats(self, samplePeriod):
        if self.samples:
            firstSample = self.samples[0]
            lastSample = self.samples[-1]
            self.start_time = min(firstSample.time, self.start_time)
            # self.duration is the _minimum_ known duration of the thread
            self.duration = lastSample.time - self.start_time

        self.sleepingCount =  sum([1 for sample in self.samples if sample.state == 'S'])

    def calc_load(self, userCpu, sysCpu, delayacct_blkio_ticks, interval, num_cpus):
        downscale = interval * num_cpus
        # all args in units of clock ticks
        userCpuLoad = float(userCpu - self.user_cpu_ticks[-1]) / downscale
        sysCpuLoad = float(sysCpu - self.sys_cpu_ticks[-1]) / downscale
        delayacctBlkioLoad = float(delayacct_blkio_ticks - self.delayacct_blkio_ticks[-1]) / downscale
        return (userCpuLoad, sysCpuLoad, delayacctBlkioLoad)

    def set_parent(self, processMap):
        if self.ppid != None:
            self.parent = processMap.get (self.ppid)
            if self.parent == None and self.pid / 1000 > 1 and \
                not (self.ppid/PID_SCALE == 2 or self.pid/PID_SCALE == 2): # kernel threads: ppid=2
                writer.warn("Missing CONFIG_PROC_EVENTS: no parent for pid '%i' ('%s') with ppid '%i'" \
                                % (self.pid,self.cmd,self.ppid))

    def get_end_time(self):
        return self.start_time + self.duration

    def set_cmd(self, cmd):
        cmd = cmd.strip('()')
        # In case the collector writes the executable's pathname into the 'comm' field
        # of /proc/[pid]/stat, strip off all but the basename, to preserve screen space
        # -- but some kernel threads are named like so 'ksoftirqd/0'.  Hack around
        # this by carving out an exception for all children of 'kthreadd'
        kthreadd_pid = 2 * PID_SCALE
        self.cmd = cmd.split('/')[-1] if self.ppid != kthreadd_pid else cmd

    def set_nice(self, nice):
        self.nice = nice
