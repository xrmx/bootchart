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

class EventSample:
    def __init__(self, time, time_usec, pid, tid, comm, match, raw_log_file, raw_log_seek):
        self.time = time
        self.time_usec = time_usec
        self.pid = pid
        self.tid = tid
        self.comm = comm
        self.match = match
        self.raw_log_file = raw_log_file  # a File object
        self.raw_log_seek = raw_log_seek

    def raw_log_line(self):
        def _readline(file, raw_log_seek):
            if not file:
                return
            file.seek(raw_log_seek)
            line = file.readline()
            return line
        return _readline(self.raw_log_file, self.raw_log_seek)



class DiskStatSample:
    def __init__(self, time):
        self.time = time
        self.diskdata = [0, 0, 0]
    def add_diskdata(self, new_diskdata):
        self.diskdata = [ a + b for a, b in zip(self.diskdata, new_diskdata) ]

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
    def __init__(self, writer, process_map, sample_count, sample_period, start_time, end_time):
        self.process_map = process_map
        self.sample_count = sample_count
        self.sample_period = sample_period
        self.start_time = start_time   # time at which the first sample was collected
        self.end_time = end_time
        writer.info ("%d samples, avg. sample length %f" % (self.sample_count, self.sample_period))
        writer.info ("process list size: %d" % len (self.process_map.values()))

class Process:
    def __init__(self, writer, pid, tid, cmd, ppid, start_time):
        self.writer = writer
        self.pid = pid
        self.tid = tid
        self.cmd = cmd
        self.exe = cmd
        self.args = []
        self.ppid = ppid
        self.start_time = start_time
        self.duration = 0
        self.samples = []        # list of ProcessCPUSample
        self.events = []         # time-ordered list of EventSample
        self.parent = None
        self.child_list = []

        self.user_cpu_ticks = [None, None]    # [first, last]
        self.sys_cpu_ticks = [None, None]

        # For transient use as an accumulator during early parsing -- when
        # concurrent samples of all threads can be accessed O(1).
        self.missing_child_ticks = None

        self.last_cpu_ns = 0
        self.last_blkio_delay_ns = 0
        self.last_swapin_delay_ns = 0

        # dynamic, view-dependent per-process state boolean
        self.draw = True

    def cpu_tick_count_during_run(self):
        ''' total CPU clock ticks reported for this process during the profiling run'''
        return self.user_cpu_ticks[-1] + self.sys_cpu_ticks[-1] \
                        - (self.user_cpu_ticks[0] + self.sys_cpu_ticks[0])

    # split this process' run - triggered by a name change
    #  XX  called only if taskstats.log is provided (bootchart2 daemon)
    def split(self, writer, pid, cmd, ppid, start_time):
        split = Process (writer, pid, cmd, ppid, start_time)

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

        # XX  add in page faults, including "minor"
        self.activeCount = sum( [1 for sample in self.samples if sample.state != 'S'])

    def calc_load(self, userCpu, sysCpu, interval):
        # all args in units of clock ticks
        userCpuLoad = float(userCpu - self.user_cpu_ticks[-1]) / interval
        sysCpuLoad = float(sysCpu - self.sys_cpu_ticks[-1]) / interval
        return (userCpuLoad, sysCpuLoad)

    def set_parent(self, processMap):
        if self.ppid != None:
            self.parent = processMap.get (self.ppid)
            if self.parent == None and self.pid / 1000 > 1 and \
                not (self.ppid == 2000 or self.pid == 2000): # kernel threads: ppid=2
                self.writer.warn("Missing CONFIG_PROC_EVENTS: no parent for pid '%i' ('%s') with ppid '%i'" \
                                 % (self.pid,self.cmd,self.ppid))

    def get_end_time(self):
        return self.start_time + self.duration

# To understand 'io_ticks', see the kernel's part_round_stats_single() and part_round_stats()
class DiskSample:
    def __init__(self, time, read, write, io_ticks):
        self.time = time
        self.read = read    # sectors, a delta relative to the preceding time
        self.write = write  #     ~
        self.util = io_ticks    # a delta, units of msec
        self.tput = read + write

class DiskSamples:
    def __init__(self, name, samples):
        self.name = name
        self.samples = samples
#
#    def __str__(self):
#        return "\t".join([str(self.time), str(self.read), str(self.write), str(self.util)])
