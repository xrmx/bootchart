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


import cairo
import math
import re
import random
import colorsys

class RenderOptions:

	def __init__(self, app_options):
		# should we render a cumulative CPU time chart
		self.cumulative = True
		self.charts = True
		self.kernel_only = False
		self.app_options = app_options

	def proc_tree (self, trace):
		if self.kernel_only:
			return trace.kernel_tree
		else:
			return trace.proc_tree

# Process tree background color.
BACK_COLOR = (1.0, 1.0, 1.0, 1.0)

WHITE = (1.0, 1.0, 1.0, 1.0)
# Process tree border color.
BORDER_COLOR = (0.63, 0.63, 0.63, 1.0)
# Second tick line color.
TICK_COLOR = (0.92, 0.92, 0.92, 1.0)
# 5-second tick line color.
TICK_COLOR_BOLD = (0.86, 0.86, 0.86, 1.0)
# Annotation colour
ANNOTATION_COLOR = (0.63, 0.0, 0.0, 0.5)
# Text color.
TEXT_COLOR = (0.0, 0.0, 0.0, 1.0)

# Font family
FONT_NAME = "Bitstream Vera Sans"
# Title text font.
TITLE_FONT_SIZE = 18
# Default text font.
TEXT_FONT_SIZE = 12
# Axis label font.
AXIS_FONT_SIZE = 11
# Legend font.
LEGEND_FONT_SIZE = 12

# CPU load chart color.
CPU_COLOR = (0.40, 0.55, 0.70, 1.0)
# IO wait chart color.
IO_COLOR = (0.76, 0.48, 0.48, 0.5)
# Disk throughput color.
DISK_TPUT_COLOR = (0.20, 0.71, 0.20, 1.0)
# CPU load chart color.
FILE_OPEN_COLOR = (0.20, 0.71, 0.71, 1.0)
# Mem cached color
MEM_CACHED_COLOR = CPU_COLOR
# Mem used color
MEM_USED_COLOR = IO_COLOR
# Buffers color
MEM_BUFFERS_COLOR = (0.4, 0.4, 0.4, 0.3)
# Swap color
MEM_SWAP_COLOR = DISK_TPUT_COLOR

# Process border color.
PROC_BORDER_COLOR = (0.71, 0.71, 0.71, 1.0)
# Waiting process color.
PROC_COLOR_D = (0.76, 0.48, 0.48, 0.5)
# Running process color.
PROC_COLOR_R = CPU_COLOR
# Sleeping process color.
PROC_COLOR_S = (0.94, 0.94, 0.94, 1.0)
# Stopped process color.
PROC_COLOR_T = (0.94, 0.50, 0.50, 1.0)
# Zombie process color.
PROC_COLOR_Z = (0.71, 0.71, 0.71, 1.0)
# Dead process color.
PROC_COLOR_X = (0.71, 0.71, 0.71, 0.125)
# Paging process color.
PROC_COLOR_W = (0.71, 0.71, 0.71, 0.125)

# Process label color.
PROC_TEXT_COLOR = (0.19, 0.19, 0.19, 1.0)
# Process label font.
PROC_TEXT_FONT_SIZE = 12

# Signature color.
SIG_COLOR = (0.0, 0.0, 0.0, 0.3125)
# Signature font.
SIG_FONT_SIZE = 14
# Signature text.
SIGNATURE = "http://github.com/mmeeks/bootchart"

# Process dependency line color.
DEP_COLOR = (0.75, 0.75, 0.75, 1.0)
# Process dependency line stroke.
DEP_STROKE = 1.0

# Process description date format.
DESC_TIME_FORMAT = "mm:ss.SSS"

# Cumulative coloring bits
HSV_MAX_MOD = 31
HSV_STEP = 7

# Process states
STATE_UNDEFINED = 0
STATE_RUNNING   = 1
STATE_SLEEPING  = 2
STATE_WAITING   = 3
STATE_STOPPED   = 4
STATE_ZOMBIE    = 5

STATE_COLORS = [(0, 0, 0, 0), PROC_COLOR_R, PROC_COLOR_S, PROC_COLOR_D, \
		PROC_COLOR_T, PROC_COLOR_Z, PROC_COLOR_X, PROC_COLOR_W]

# CumulativeStats Types
STAT_TYPE_CPU = 0
STAT_TYPE_IO = 1

# Convert ps process state to an int
def get_proc_state(flag):
	return "RSDTZXW".find(flag) + 1

bar_h = 55
meminfo_bar_h = 2 * bar_h
header_h = 110 + 2 * (30 + bar_h) + 1 * (30 + meminfo_bar_h)
# offsets
off_x, off_y = 10, 10
sec_w_base = 50 # the width of a second
proc_h = 16 # the height of a process
leg_s = 10
MIN_IMG_W = 800
CUML_HEIGHT = 2000 # Increased value to accomodate CPU and I/O Graphs

def extents(options, xscale, trace):
	proc_tree = options.proc_tree(trace)
	w = int (proc_tree.duration * sec_w_base * xscale / 100) + 2*off_x
	h = proc_h * proc_tree.num_proc + 2 * off_y
	if options.charts:
		h += header_h
	if proc_tree.taskstats and options.cumulative:
		h += CUML_HEIGHT + 4 * off_y
	return (w, h)

def clip_visible(clip, rect):
	xmax = max (clip[0], rect[0])
	ymax = max (clip[1], rect[1])
	xmin = min (clip[0] + clip[2], rect[0] + rect[2])
	ymin = min (clip[1] + clip[3], rect[1] + rect[3])
	return (xmin > xmax and ymin > ymax)

# elide the bootchart collector - it is quite distorting
def elide_bootchart(proc):
	return proc.cmd == 'bootchartd' or proc.cmd == 'bootchart-colle'

class CumlSample:
	def __init__(self, proc):
		self.cmd = proc.cmd
		self.samples = []
		self.merge_samples (proc)
		self.color = None

	def merge_samples(self, proc):
		self.samples.extend (proc.samples)
		self.samples.sort (key = lambda p: p.time)

	def next(self):
		global palette_idx
		palette_idx += HSV_STEP
		return palette_idx

	def get_color(self):
		if self.color is None:
			i = self.next() % HSV_MAX_MOD
			h = 0.0
			if i is not 0:
				h = (1.0 * i) / HSV_MAX_MOD
			s = 0.5
			v = 1.0
			c = colorsys.hsv_to_rgb (h, s, v)
			self.color = (c[0], c[1], c[2], 1.0)
		return self.color

class Draw:
	def __init__(self, ctx, options, trace):
		self.ctx = ctx
		self.options = options
		self.trace = trace
		self.app_options = options.app_options

	def text(self, text, color, x, y):
		self.ctx.set_source_rgba(*color)
		self.ctx.move_to(x, y)
		self.ctx.show_text(text)

	def fill_rect(self, color, rect):
		self.ctx.set_source_rgba(*color)
		self.ctx.rectangle(*rect)
		self.ctx.fill()

	def rect(self, color, rect):
		self.ctx.set_source_rgba(*color)
		self.ctx.rectangle(*rect)
		self.ctx.stroke()

	def legend_box(self, label, fill_color, x, y, s):
		self.fill_rect(fill_color, (x, y - s, s, s))
		self.rect(PROC_BORDER_COLOR, (x, y - s, s, s))
		self.text(label, TEXT_COLOR, x + s + 5, y)

	def legend_line(self, label, fill_color, x, y, s):
		self.fill_rect(fill_color, (x, y - s/2, s + 1, 3))
		self.ctx.arc(x + (s + 1)/2.0, y - (s - 3)/2.0, 2.5, 0, 2.0 * math.pi)
		self.ctx.fill()
		self.text(label, TEXT_COLOR, x + s + 5, y)

	def label_in_box(self, color, label, x, y, w, maxx):
		label_w = self.ctx.text_extents(label)[2]
		label_x = x + w / 2 - label_w / 2
		if label_w + 10 > w:
			label_x = x + w + 5
		if label_x + label_w > maxx:
			label_x = x - label_w - 5
		self.text(label, color, label_x, y)

	def sec_labels(self, rect, sec_w, nsecs):
		self.ctx.set_font_size(AXIS_FONT_SIZE)
		prev_x = 0
		for i in range(0, rect[2] + 1, sec_w):
			if ((i / sec_w) % nsecs == 0) :
				label = "%ds" % (i / sec_w)
				label_w = self.ctx.text_extents(label)[2]
				x = rect[0] + i - label_w/2
				if x >= prev_x:
					self.text(label, TEXT_COLOR, x, rect[1] - 2)
					prev_x = x + label_w

	def box_ticks(self, rect, sec_w):
		self.rect(BORDER_COLOR, tuple(rect))

		self.ctx.set_line_cap(cairo.LINE_CAP_SQUARE)

		for i in range(sec_w, rect[2] + 1, sec_w):
			if ((i / sec_w) % 5 == 0) :
				self.ctx.set_source_rgba(*TICK_COLOR_BOLD)
			else :
				self.ctx.set_source_rgba(*TICK_COLOR)
			self.ctx.move_to(rect[0] + i, rect[1] + 1)
			self.ctx.line_to(rect[0] + i, rect[1] + rect[3] - 1)
			self.ctx.stroke()

		self.ctx.set_line_cap(cairo.LINE_CAP_BUTT)

	def annotations(self, proc_tree, times, rect):
		self.ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
		self.ctx.set_source_rgba(*ANNOTATION_COLOR)
		self.ctx.set_dash([4, 4])

		for time in times:
			if time is not None:
				x = ((time - proc_tree.start_time) * rect[2] / proc_tree.duration)

				self.ctx.move_to(rect[0] + x, rect[1] + 1)
				self.ctx.line_to(rect[0] + x, rect[1] + rect[3] - 1)
				self.ctx.stroke()

		self.ctx.set_line_cap(cairo.LINE_CAP_BUTT)
		self.ctx.set_dash([])

	def chart(self, color, fill, chart_bounds, data, proc_tree, data_range):
		self.ctx.set_line_width(0.5)
		x_shift = proc_tree.start_time

		def transform_point_coords(point, x_base, y_base, \
					   xscale, yscale, x_trans, y_trans):
			x = (point[0] - x_base) * xscale + x_trans
			y = (point[1] - y_base) * -yscale + y_trans + chart_bounds[3]
			return x, y

		max_x = max (x for (x, y) in data)
		max_y = max (y for (x, y) in data)
		# avoid divide by zero
		if max_y == 0:
			max_y = 1.0
		xscale = float (chart_bounds[2]) / max_x
		# If data_range is given, scale the chart so that the value range in
		# data_range matches the chart bounds exactly.
		# Otherwise, scale so that the actual data matches the chart bounds.
		if data_range:
			yscale = float(chart_bounds[3]) / (data_range[1] - data_range[0])
			ybase = data_range[0]
		else:
			yscale = float(chart_bounds[3]) / max_y
			ybase = 0

		first = transform_point_coords (data[0], x_shift, ybase, xscale, yscale, \
					        chart_bounds[0], chart_bounds[1])
		last =  transform_point_coords (data[-1], x_shift, ybase, xscale, yscale, \
					        chart_bounds[0], chart_bounds[1])

		self.ctx.set_source_rgba(*color)
		self.ctx.move_to(*first)
		for point in data:
			x, y = transform_point_coords (point, x_shift, ybase, xscale, yscale, \
						       chart_bounds[0], chart_bounds[1])
			self.ctx.line_to(x, y)
		if fill:
			self.ctx.stroke_preserve()
			self.ctx.line_to(last[0], chart_bounds[1]+chart_bounds[3])
			self.ctx.line_to(first[0], chart_bounds[1]+chart_bounds[3])
			self.ctx.line_to(first[0], first[1])
			self.ctx.fill()
		else:
			self.ctx.stroke()
		self.ctx.set_line_width(1.0)

	def render_charts(self, options, clip, trace, curr_y, w, h, sec_w):
		proc_tree = options.proc_tree(trace)

		# render bar legend
		self.ctx.set_font_size(LEGEND_FONT_SIZE)

		self.legend_box("CPU (user+sys)", CPU_COLOR, off_x, curr_y+20, leg_s)
		self.legend_box("I/O (wait)", IO_COLOR, off_x + 120, curr_y+20, leg_s)

		# render I/O wait
		chart_rect = (off_x, curr_y+30, w, bar_h)
		if clip_visible(clip, chart_rect):
			self.box_ticks(chart_rect, sec_w)
			self.annotations(proc_tree, trace.times, chart_rect)
			self.chart(IO_COLOR, True, chart_rect, \
				   [(sample.time, sample.user + sample.sys + sample.io) for sample in trace.cpu_stats], \
				   proc_tree, None)
			# render CPU load
			self.chart(CPU_COLOR, True, chart_rect, \
				   [(sample.time, sample.user + sample.sys) for sample in trace.cpu_stats], \
				   proc_tree, None)

		curr_y = curr_y + 30 + bar_h

		# render second chart
		self.legend_line("Disk throughput", DISK_TPUT_COLOR, off_x, curr_y+20, leg_s)
		self.legend_box("Disk utilization", IO_COLOR, off_x + 120, curr_y+20, leg_s)

		# render I/O utilization
		chart_rect = (off_x, curr_y+30, w, bar_h)
		if clip_visible (clip, chart_rect):
			self.box_ticks (chart_rect, sec_w)
			self.annotations (proc_tree, trace.times, chart_rect)
			self.chart (IO_COLOR, True, chart_rect, \
				    [(sample.time, sample.util) for sample in trace.disk_stats], \
				    proc_tree, None)

		# render disk throughput
		max_sample = max (trace.disk_stats, key = lambda s: s.tput)
		if clip_visible (clip, chart_rect):
			self.chart (DISK_TPUT_COLOR, False, chart_rect, \
				    [(sample.time, sample.tput) for sample in trace.disk_stats], \
				    proc_tree, None)

		pos_x = off_x + ((max_sample.time - proc_tree.start_time) * w / proc_tree.duration)

		shift_x, shift_y = -20, 20
		if (pos_x < off_x + 245):
			shift_x, shift_y = 5, 40

		label = "%dMB/s" % round ((max_sample.tput) / 1024.0)
		self.text (label, DISK_TPUT_COLOR, pos_x + shift_x, curr_y + shift_y)

		curr_y = curr_y + 30 + bar_h

		# render mem usage
		chart_rect = (off_x, curr_y+30, w, meminfo_bar_h)
		mem_stats = trace.mem_stats
		if mem_stats and clip_visible (clip, chart_rect):
			mem_scale = max(sample.records['MemTotal'] - sample.records['MemFree'] for sample in mem_stats)
			self.legend_box("Mem cached (scale: %u MiB)" % (float(mem_scale) / 1024), MEM_CACHED_COLOR, off_x, curr_y+20, leg_s)
			self.legend_box("Used", MEM_USED_COLOR, off_x + 240, curr_y+20, leg_s)
			self.legend_box("Buffers", MEM_BUFFERS_COLOR, off_x + 360, curr_y+20, leg_s)
			self.legend_line("Swap (scale: %u MiB)" % max([(sample.records['SwapTotal'] - sample.records['SwapFree'])/1024 for sample in mem_stats]), \
					 MEM_SWAP_COLOR, off_x + 480, curr_y+20, leg_s)
			self.box_ticks(chart_rect, sec_w)
			self.annotations(proc_tree, trace.times, chart_rect)
			self.chart(MEM_BUFFERS_COLOR, True, chart_rect, \
				   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree']) for sample in trace.mem_stats], \
				   proc_tree, [0, mem_scale])
			self.chart(MEM_USED_COLOR, True, chart_rect, \
				   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree'] - sample.records['Buffers']) for sample in mem_stats], \
				   proc_tree, [0, mem_scale])
			self.chart(MEM_CACHED_COLOR, True, chart_rect, \
				   [(sample.time, sample.records['Cached']) for sample in mem_stats], \
				   proc_tree, [0, mem_scale])
			self.chart(MEM_SWAP_COLOR, False, chart_rect, \
				   [(sample.time, float(sample.records['SwapTotal'] - sample.records['SwapFree'])) for sample in mem_stats], \
				   proc_tree, None)

			curr_y = curr_y + meminfo_bar_h

		return curr_y

	#
	# Render the chart.
	#
	def render(self, xscale):
		(w, h) = extents (self.options, xscale, self.trace)

		proc_tree = self.options.proc_tree (self.trace)

		# x, y, w, h
		clip = self.ctx.clip_extents()

		sec_w = int (xscale * sec_w_base)
		self.ctx.set_line_width(1.0)
		self.ctx.select_font_face(FONT_NAME)
		self.fill_rect(WHITE, (0, 0, max(w, MIN_IMG_W), h))
		w -= 2*off_x
		# draw the title and headers
		if proc_tree.idle:
			duration = proc_tree.idle
		else:
			duration = proc_tree.duration

		if not self.options.kernel_only:
			curr_y = self.draw_header (self.trace.headers, duration)
		else:
			curr_y = off_y;

		if self.options.charts:
			curr_y = self.render_charts (self.options, clip, self.trace, curr_y, w, h, sec_w)

		# draw process boxes
		proc_height = h
		if proc_tree.taskstats and self.options.cumulative:
			proc_height -= CUML_HEIGHT

		self.draw_process_bar_chart(clip, self.options, proc_tree, self.trace.times,
					    curr_y, w, proc_height, sec_w)

		curr_y = proc_height
		self.ctx.set_font_size(SIG_FONT_SIZE)
		self.text(SIGNATURE, SIG_COLOR, off_x + 5, proc_height - 8)

		# draw a cumulative CPU-time-per-process graph
		if proc_tree.taskstats and self.options.cumulative:
			cuml_rect = (off_x, curr_y + off_y, w, CUML_HEIGHT/2 - off_y * 2)
			if clip_visible (clip, cuml_rect):
				self.cuml_graph(proc_tree, cuml_rect, duration, sec_w, STAT_TYPE_CPU)

		# draw a cumulative I/O-time-per-process graph
		if proc_tree.taskstats and self.options.cumulative:
			cuml_rect = (off_x, curr_y + off_y * 100, w, CUML_HEIGHT/2 - off_y * 2)
			if clip_visible (clip, cuml_rect):
				self.cuml_graph(proc_tree, cuml_rect, duration, sec_w, STAT_TYPE_IO)

	def draw_process_bar_chart(self, clip, options, proc_tree, times, curr_y, w, h, sec_w):
		header_size = 0
		if not options.kernel_only:
			self.legend_box ("Running (%cpu)",
					 PROC_COLOR_R, off_x    , curr_y + 45, leg_s)
			self.legend_box ("Unint.sleep (I/O)",
					 PROC_COLOR_D, off_x+120, curr_y + 45, leg_s)
			self.legend_box ("Sleeping",
					 PROC_COLOR_S, off_x+240, curr_y + 45, leg_s)
			self.legend_box ("Zombie",
					 PROC_COLOR_Z, off_x+360, curr_y + 45, leg_s)
			header_size = 45

		chart_rect = [off_x, curr_y + header_size + 15,
			      w, h - 2 * off_y - (curr_y + header_size + 15) + proc_h]
		self.ctx.set_font_size (PROC_TEXT_FONT_SIZE)

		self.box_ticks (chart_rect, sec_w)
		if sec_w > 100:
			nsec = 1
		else:
			nsec = 5
		self.sec_labels (chart_rect, sec_w, nsec)
		self.annotations (proc_tree, times, chart_rect)

		y = curr_y + 60
		for root in proc_tree.process_tree:
			self.draw_processes_recursively(root, proc_tree, y, proc_h, chart_rect, clip)
			y = y + proc_h * proc_tree.num_nodes([root])

	def draw_header (self, headers, duration):
		toshow = [
			('system.uname', 'uname', lambda s: s),
			('system.release', 'release', lambda s: s),
			('system.cpu', 'CPU', lambda s: re.sub('model name\s*:\s*', '', s, 1)),
			('system.kernel.options', 'kernel options', lambda s: s),
		]

		header_y = self.ctx.font_extents()[2] + 10
		self.ctx.set_font_size(TITLE_FONT_SIZE)
		self.text(headers['title'], TEXT_COLOR, off_x, header_y)
		self.ctx.set_font_size(TEXT_FONT_SIZE)

		for (headerkey, headertitle, mangle) in toshow:
			header_y += self.ctx.font_extents()[2]
			if headerkey in headers:
				value = headers.get(headerkey)
			else:
				value = ""
			txt = headertitle + ': ' + mangle(value)
			self.text(txt, TEXT_COLOR, off_x, header_y)

		dur = duration / 100.0
		txt = 'time : %02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60))
		if headers.get('system.maxpid') is not None:
			txt = txt + '      max pid: %s' % (headers.get('system.maxpid'))

		header_y += self.ctx.font_extents()[2]
		self.text (txt, TEXT_COLOR, off_x, header_y)

		return header_y

	def draw_processes_recursively(self, proc, proc_tree, y, proc_h, rect, clip) :
		x = rect[0] +  ((proc.start_time - proc_tree.start_time) * rect[2] / proc_tree.duration)
		w = ((proc.duration) * rect[2] / proc_tree.duration)

		self.draw_process_activity_colors(proc, proc_tree, x, y, w, proc_h, rect, clip)
		self.rect(PROC_BORDER_COLOR, (x, y, w, proc_h))
		ipid = int(proc.pid)
		if not self.app_options.show_all:
			cmdString = proc.cmd
		else:
			cmdString = ''
		if (self.app_options.show_pid or self.app_options.show_all) and ipid is not 0:
			cmdString = cmdString + " [" + str(ipid / 1000) + "]"
		if self.app_options.show_all:
			if proc.args:
				cmdString = cmdString + " '" + "' '".join(proc.args) + "'"
			else:
				cmdString = cmdString + " " + proc.exe

		self.label_in_box(PROC_TEXT_COLOR, cmdString, x, y + proc_h - 4, w, rect[0] + rect[2])

		next_y = y + proc_h
		for child in proc.child_list:
			if next_y > clip[1] + clip[3]:
				break
			child_x, child_y = self.draw_processes_recursively(child, proc_tree, next_y, proc_h, rect, clip)
			self.draw_process_connecting_lines(x, y, child_x, child_y, proc_h)
			next_y = next_y + proc_h * proc_tree.num_nodes([child])

		return x, y


	def draw_process_activity_colors(self, proc, proc_tree, x, y, w, proc_h, rect, clip):

		if y > clip[1] + clip[3] or y + proc_h + 2 < clip[1]:
			return

		self.fill_rect(PROC_COLOR_S, (x, y, w, proc_h))

		last_tx = -1
		for sample in proc.samples :
			tx = rect[0] + round(((sample.time - proc_tree.start_time) * rect[2] / proc_tree.duration))

			# samples are sorted chronologically
			if tx < clip[0]:
				continue
			if tx > clip[0] + clip[2]:
				break

			tw = round(proc_tree.sample_period * rect[2] / float(proc_tree.duration))
			if last_tx != -1 and abs(last_tx - tx) <= tw:
				tw -= last_tx - tx
				tx = last_tx
			tw = max (tw, 1) # nice to see at least something

			last_tx = tx + tw
			state = get_proc_state( sample.state )

			color = STATE_COLORS[state]
			if state == STATE_RUNNING:
				alpha = min (sample.cpu_sample.user + sample.cpu_sample.sys, 1.0)
				color = tuple(list(PROC_COLOR_R[0:3]) + [alpha])
				#print "render time %d [ tx %d tw %d ], sample state %s color %s alpha %g" % (sample.time, tx, tw, state, color, alpha)
			elif state == STATE_SLEEPING:
				continue

			self.fill_rect(color, (tx, y, tw, proc_h))

	def draw_process_connecting_lines(self, px, py, x, y, proc_h):
		self.ctx.set_source_rgba(*DEP_COLOR)
		self.ctx.set_dash([2, 2])
		if abs(px - x) < 3:
			dep_off_x = 3
			dep_off_y = proc_h / 4
			self.ctx.move_to(x, y + proc_h / 2)
			self.ctx.line_to(px - dep_off_x, y + proc_h / 2)
			self.ctx.line_to(px - dep_off_x, py - dep_off_y)
			self.ctx.line_to(px, py - dep_off_y)
		else:
			self.ctx.move_to(x, y + proc_h / 2)
			self.ctx.line_to(px, y + proc_h / 2)
			self.ctx.line_to(px, py)
		self.ctx.stroke()
		self.ctx.set_dash([])


	def cuml_graph(self, proc_tree, chart_bounds, duration, sec_w, stat_type):
		global palette_idx
		palette_idx = 0

		time_hash = {}
		total_time = 0.0
		m_proc_list = {}

		if stat_type is STAT_TYPE_CPU:
			sample_value = 'cpu'
		else:
			sample_value = 'io'
		for proc in proc_tree.process_list:
			if elide_bootchart(proc):
				continue

			for sample in proc.samples:
				total_time += getattr(sample.cpu_sample, sample_value)
				if not sample.time in time_hash:
					time_hash[sample.time] = 1

			# merge pids with the same cmd
			if not proc.cmd in m_proc_list:
				m_proc_list[proc.cmd] = CumlSample (proc)
				continue
			s = m_proc_list[proc.cmd]
			s.merge_samples (proc)

		# all the sample times
		times = time_hash.keys()
		times.sort()
		if len (times) < 2:
			print("degenerate boot chart")
			return

		pix_per_ns = chart_bounds[3] / total_time
		#print "total time: %g pix-per-ns %g" % (total_time, pix_per_ns)

		# FIXME: we have duplicates in the process list too [!] - why !?

		# Render bottom up, left to right
		below = {}
		for time in times:
			below[time] = chart_bounds[1] + chart_bounds[3]

		# same colors each time we render
		random.seed (0)

		self.ctx.set_line_width(1)

		legends = []
		labels = []

		# render each pid in order
		for cs in m_proc_list.values():
			row = {}
			cuml = 0.0

			# print "pid : %s -> %g samples %d" % (proc.cmd, cuml, len (cs.samples))
			for sample in cs.samples:
				cuml += getattr(sample.cpu_sample, sample_value)
				row[sample.time] = cuml

			process_total_time = cuml

			# hide really tiny processes
			if cuml * pix_per_ns <= 2:
				continue

			last_time = times[0]
			y = last_below = below[last_time]
			last_cuml = cuml = 0.0

			self.ctx.set_source_rgba(*cs.get_color())
			for time in times:
				render_seg = False

				# did the underlying trend increase ?
				if below[time] != last_below:
					last_below = below[last_time]
					last_cuml = cuml
					render_seg = True

				# did we move up a pixel increase ?
				if time in row:
					nc = round (row[time] * pix_per_ns)
					if nc != cuml:
						last_cuml = cuml
						cuml = nc
						render_seg = True

				#if last_cuml > cuml:
				#	assert fail ... - un-sorted process samples

				# draw the trailing rectangle from the last time to
				# before now, at the height of the last segment.
				if render_seg:
					w = math.ceil ((time - last_time) * chart_bounds[2] / proc_tree.duration) + 1
					x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration)
					self.ctx.rectangle (x, below[last_time] - last_cuml, w, last_cuml)
					self.ctx.fill()
					#self.ctx.stroke()
					last_time = time
					y = below [time] - cuml

				row[time] = y

			# render the last segment
			x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration)
			y = below[last_time] - cuml
			self.ctx.rectangle (x, y, chart_bounds[2] - x, cuml)
			self.ctx.fill()
			#ctx.stroke()

			# render legend if it will fit
			if cuml > 8:
				label = cs.cmd
				extnts = self.ctx.text_extents(label)
				label_w = extnts[2]
				label_h = extnts[3]
				#print "Text extents %g by %g" % (label_w, label_h)
				labels.append((label,
					       chart_bounds[0] + chart_bounds[2] - label_w - off_x * 2,
					       y + (cuml + label_h) / 2))
				if cs in legends:
					print("ARGH - duplicate process in list !")

			legends.append ((cs, process_total_time))

			below = row

		# render grid-lines over the top
		self.box_ticks(chart_bounds, sec_w)

		# render labels
		for l in labels:
			self.text(l[0], TEXT_COLOR, l[1], l[2])

		# Render legends
		font_height = 20
		label_width = 300
		LEGENDS_PER_COL = 15
		LEGENDS_TOTAL = 45
		self.ctx.set_font_size (TITLE_FONT_SIZE)
		dur_secs = duration / 100
		cpu_secs = total_time / 1000000000

		# misleading - with multiple CPUs ...
		#	idle = ((dur_secs - cpu_secs) / dur_secs) * 100.0
		if stat_type is STAT_TYPE_CPU:
			label = "Cumulative CPU usage, by process; total CPU: " \
				" %.5g(s) time: %.3g(s)" % (cpu_secs, dur_secs)
		else:
			label = "Cumulative I/O usage, by process; total I/O: " \
				" %.5g(s) time: %.3g(s)" % (cpu_secs, dur_secs)

		self.text(label, TEXT_COLOR, chart_bounds[0] + off_x,
			  chart_bounds[1] + font_height)

		i = 0
		legends.sort(lambda a, b: cmp (b[1], a[1]))
		self.ctx.set_font_size(TEXT_FONT_SIZE)
		for t in legends:
			cs = t[0]
			time = t[1]
			x = chart_bounds[0] + off_x + int (i/LEGENDS_PER_COL) * label_width
			y = chart_bounds[1] + font_height * ((i % LEGENDS_PER_COL) + 2)
			str = "%s - %.0f(ms) (%2.2f%%)" % (cs.cmd, time/1000000, (time/total_time) * 100.0)
			self.legend_box(str, cs.color, x, y, leg_s)
			i = i + 1
			if i >= LEGENDS_TOTAL:
				break

