#!/usr/bin/env python

import sys
import os.path
import csv

MIN_PROCESS_TIME = 8

def _do_parse_poky(state, filename):
    #print filename
    #writer.status("parsing '%s'" % filename)
    paths = filename.split("/")
    task = paths[-1]
    pn = paths[-2]
    start = None
    end = None
    with open(filename, "rb") as file:
        for line in file:
            if line.startswith("Started:"):
                start = float(line.split()[-1])
            elif line.startswith("Ended:"):
                end = float(line.split()[-1])
        if start and end and (end - start) > MIN_PROCESS_TIME:
            state.processes[pn + ":" + task] = [start, end]
            state.start[start] = pn + ":" + task
    return state

def parse_paths(state, paths):
    for path in paths:
        if not os.path.exists(path):
            print "path %s does not exists"
            continue
        if os.path.isdir(path):
            files = sorted([os.path.join(path, f) for f in os.listdir(path)])
            state = parse_paths(state, files)
        else:
            state = _do_parse_poky(state, path)
    return state

class State:
    def __init__(self):
        self.processes = {}
        self.start = {}

class Process:
    def __init__(self, state, key):
        p_id = state.start[key]
        p = state.processes[p_id]

        self.pn = p_id.split(':')[0]
        self.task = p_id.split(':')[1]
        self.start = p[0]
        self.end = p[1]

if __name__ == '__main__':
    state = State()
    parse_paths(state, sys.argv[1:])

    process_list = []
    sato = csv.writer(open('sato.log', 'wb'), delimiter='\t', quoting=csv.QUOTE_NONE)
    for k in sorted(state.start.keys(), key=lambda t: float(t)):
       proc = Process(state, k)
       sato.writerow([proc.start, proc.end, proc.task, proc.pn])
