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
CPU_COLOR = (0.60, 0.65, 0.75, 1.0)
# IO wait chart color.
IO_COLOR = (0.76, 0.48, 0.48, 0.5)
PROCS_RUNNING_COLOR = (0.0, 1.0, 0.0, 1.0)
PROCS_BLOCKED_COLOR = (0.7, 0.0, 0.0, 1.0)

# Disk throughput color.
DISK_TPUT_COLOR = (0.20, 0.71, 0.20, 1.0)
# Disk throughput color.
DISK_WRITE_COLOR = (0.7, 0.0, 0.7, 1.0)
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
PROC_COLOR_D = PROCS_BLOCKED_COLOR   # (0.76, 0.45, 0.35, 1.0)
# Running process color.
PROC_COLOR_R = CPU_COLOR   # (0.40, 0.50, 0.80, 1.0)  # should look similar to CPU_COLOR
# Sleeping process color.
PROC_COLOR_S = (0.95, 0.95, 0.95, 1.0)
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

# Event tick color.
EVENT_COLOR = (0.0, 0.0, 0.0, 1.0)

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
STATE_RUNNING   = 1  # useful state info
STATE_SLEEPING  = 2
STATE_WAITING   = 3  # useful state info
STATE_STOPPED   = 4
STATE_ZOMBIE    = 5

STATE_COLORS = [(0, 0, 0, 0), PROCS_RUNNING_COLOR, PROC_COLOR_S, PROC_COLOR_D, \
		PROC_COLOR_T, PROC_COLOR_Z, PROC_COLOR_X, PROC_COLOR_W]

JUSTIFY_LEFT = "left"

# CumulativeStats Types
STAT_TYPE_CPU = 0
STAT_TYPE_IO = 1

# Convert ps process state to an int
def get_proc_state(flag):
	return "RSDTZXW".find(flag) + 1

def draw_text(ctx, text, color, x, y):
	ctx.set_source_rgba(*color)
	ctx.move_to(x, y)
	ctx.show_text(text)

def draw_fill_rect(ctx, color, rect):
	ctx.set_source_rgba(*color)
	ctx.rectangle(*rect)
	ctx.fill()

def draw_rect(ctx, color, rect):
	ctx.set_source_rgba(*color)
	ctx.rectangle(*rect)
	ctx.stroke()

def draw_diamond(ctx, x, y, w, h):
	ctx.save()
	ctx.set_line_width(0.0)
	ctx.move_to(x-w/2, y)
	ctx.line_to(x, y+h/2)
	ctx.line_to(x+w/2, y)
	ctx.line_to(x, y-h/2)
	ctx.line_to(x-w/2, y)
	ctx.fill()
	ctx.restore()

def draw_legend_diamond(ctx, label, fill_color, x, y, w, h):
	ctx.set_source_rgba(*fill_color)
	draw_diamond(ctx, x, y-h/2, w, h)
	draw_text(ctx, label, TEXT_COLOR, x + w + 5, y)

def draw_legend_box(ctx, label, fill_color, x, y, s):
	draw_fill_rect(ctx, fill_color, (x, y - s, s, s))
	#draw_rect(ctx, PROC_BORDER_COLOR, (x, y - s, s, s))
	draw_text(ctx, label, TEXT_COLOR, x + s + 5, y)

def draw_legend_line(ctx, label, fill_color, x, y, s):
	draw_fill_rect(ctx, fill_color, (x, y - s/2, s + 1, 3))
	ctx.fill()
	draw_text(ctx, label, TEXT_COLOR, x + s + 5, y)

def draw_label_in_box(ctx, color, label, x, y, w, minx, maxx):
	label_w = ctx.text_extents(label)[2]
	if OPTIONS.justify == JUSTIFY_LEFT:
		label_x = x
	else:
		label_x = x + w / 2 - label_w / 2   # CENTER

	if label_w + 10 > w:                # if wider than the process box
		label_x = x + w + 5         # push outside to right
	if label_x + label_w > maxx:        # if that's too far right
		label_x = x - label_w - 5   # push outside to the left
	if label_x < minx:
		label_x = minx
	draw_text(ctx, label, color, label_x, y)

def draw_label_in_box_at_time(ctx, color, label, y, label_x):
	draw_text(ctx, label, color, label_x, y)
	return ctx.text_extents(label)[2]

def csec_to_xscaled(t_csec):
	return (t_csec-time_origin_drawn) * SEC_W / CSEC

# Solve for t_csec:
#   x = (t_csec-time_origin_drawn) * SEC_W / CSEC + off_x
#
#   x - off_x = (t_csec-time_origin_drawn) * SEC_W / CSEC
#   (x - off_x) * CSEC / SEC_W = t_csec-time_origin_drawn
#
def xscaled_to_csec(x):
	return (x - off_x) * CSEC / SEC_W + time_origin_drawn

def ctx_save__csec_to_xscaled(ctx):
	ctx.save()
	ctx.scale(float(SEC_W) / CSEC, 1.0)
	ctx.translate(-time_origin_drawn, 0.0)

def draw_sec_labels(ctx, rect, nsecs):
	ctx.set_font_size(AXIS_FONT_SIZE)
	prev_x = 0
	for i in range(0, rect[2] + 1, SEC_W):
		if ((i / SEC_W) % nsecs == 0) :
			label = "%ds" % (i / SEC_W)
			label_w = ctx.text_extents(label)[2]
			x = rect[0] + i - label_w/2
			if x >= prev_x:
				draw_text(ctx, label, TEXT_COLOR, x, rect[1] - 2)
				prev_x = x + label_w

def draw_box_ticks(ctx, rect):
	draw_rect(ctx, BORDER_COLOR, tuple(rect))
	return

	ctx.set_line_cap(cairo.LINE_CAP_SQUARE)

	for i in range(SEC_W, rect[2] + 1, SEC_W):
		if ((i / SEC_W) % 5 == 0) :
			ctx.set_source_rgba(*TICK_COLOR_BOLD)
		else :
			ctx.set_source_rgba(*TICK_COLOR)
		ctx.move_to(rect[0] + i, rect[1] + 1)
		ctx.line_to(rect[0] + i, rect[1] + rect[3] - 1)
		ctx.stroke()

	ctx.set_line_cap(cairo.LINE_CAP_BUTT)

def draw_annotations(ctx, proc_tree, times, rect):
    ctx.set_line_cap(cairo.LINE_CAP_SQUARE)
    ctx.set_source_rgba(*ANNOTATION_COLOR)
    ctx.set_dash([4, 4])

    for time in times:
        if time is not None:
            x = csec_to_xscaled(time)

            ctx.move_to(x, rect[1] + 1)
            ctx.line_to(x, rect[1] + rect[3] - 1)
            ctx.stroke()

    ctx.set_line_cap(cairo.LINE_CAP_BUTT)
    ctx.set_dash([])

def plot_line(ctx, point, x, y):
	ctx.set_line_width(1.0)
	ctx.line_to(x, y)       # rightward, and upward or downward

# backward-looking
def plot_square(ctx, point, x, y):
	ctx.set_line_width(1.0)
        ctx.line_to(ctx.get_current_point()[0], y)  # upward or downward
        ctx.line_to(x, y)  # rightward

# backward-looking
def plot_segment_positive(ctx, point, x, y):
	ctx.move_to(ctx.get_current_point()[0], y)       # upward or downward
	if point[1] <= 0:           # zero-Y samples draw nothing
		ctx.move_to(x, y)
		return
	ctx.set_line_width(1.5)
	ctx.line_to(x, y)

def plot_scatter_positive(ctx, point, x, y):
	if point[1] <= 0:
		return
	draw_diamond(ctx, x, y, 3.6, 3.6)

# All charts assumed to be full-width
def draw_chart(ctx, color, fill, chart_bounds, data, proc_tree, data_range, plot_point_func):
	def transform_point_coords(point, y_base, yscale, y_trans):
		x = csec_to_xscaled(point[0])
		y = (point[1] - y_base) * -yscale + y_trans + chart_bounds[3]
		return x, y

	max_y = max (y for (x, y) in data)
	if max_y <= 0:		# avoid divide by zero
		max_y = 1.0
	# If data_range is given, scale the chart so that the value range in
	# data_range matches the chart bounds exactly.
	# Otherwise, scale so that the actual data matches the chart bounds.
	if data_range and (data_range[1] - data_range[0]) > 0:
		yscale = float(chart_bounds[3]) / (data_range[1] - data_range[0])
		ybase = data_range[0]
	else:
		yscale = float(chart_bounds[3]) / max_y
		ybase = 0

	ctx.set_source_rgba(*color)

	# move to the x of the missing first sample point
	first = transform_point_coords ([time_origin_drawn + in_chart_X_margin(proc_tree), -9999],
					ybase, yscale, chart_bounds[1])
	ctx.move_to(first[0], first[1])

	for point in data:
		x, y = transform_point_coords (point, ybase, yscale, chart_bounds[1])
		plot_point_func(ctx, point, x, y)

	final = transform_point_coords (data[-1], ybase, yscale, chart_bounds[1])

	if fill:
		ctx.set_line_width(0.0)
		ctx.stroke_preserve()
		ctx.line_to(final[0], chart_bounds[1]+chart_bounds[3])
		ctx.line_to(first[0], chart_bounds[1]+chart_bounds[3])
		ctx.line_to(first[0], first[1])
		ctx.fill()
	else:
		ctx.stroke()
	ctx.set_line_width(1.0)

# Constants
# XX  put all of constants in a named tuple, for immutability
CSEC = 100
bar_h = 55
meminfo_bar_h = 2 * bar_h
# offsets
off_x, off_y = 10, 10
sec_w_base = 50 # the width of a second
proc_h = 16 # the height of a process
leg_s = 11
MIN_IMG_W = 800
CUML_HEIGHT = 2000 # Increased value to accomodate CPU and I/O Graphs
OPTIONS = None

SEC_W = None
time_origin_drawn = None  # time of leftmost plotted data

# window coords

def in_chart_X_margin(proc_tree):
	return proc_tree.sample_period

# Called from gui.py and batch.py, before first call to render(),
# and every time xscale changes.
# Returns size of a window capable of holding the whole scene?
def extents(options, xscale, trace):
	global OPTIONS, time_origin_drawn
	OPTIONS = options.app_options

	proc_tree = options.proc_tree(trace)
	if OPTIONS.prehistory:
		time_origin_drawn = 0  # XX  Would have to be process_tree.starttime for backwards compatibility
	else:
		time_origin_drawn = trace.cpu_stats[0].time - in_chart_X_margin(proc_tree)
	global SEC_W
	SEC_W = xscale * sec_w_base

	w = int (csec_to_xscaled(trace.cpu_stats[-1].time + in_chart_X_margin(proc_tree)) + 2*off_x)
	h = proc_h * proc_tree.num_proc + 2 * off_y
	if options.charts:
		h += 110 + (2 + len(trace.disk_stats)) * (30 + bar_h) + 1 * (30 + meminfo_bar_h)
	if proc_tree.taskstats and options.cumulative:
		h += CUML_HEIGHT + 4 * off_y
	return (w, h)  # includes off_x, off_y

def clip_visible(clip, rect):
	return True

def render_charts(ctx, options, clip, trace, curr_y, w, h):
	proc_tree = options.proc_tree(trace)

	# render bar legend
	ctx.set_font_size(LEGEND_FONT_SIZE)

	draw_legend_box(ctx, "CPU (user+sys)", CPU_COLOR, 0, curr_y+20, leg_s)
	draw_legend_box(ctx, "I/O (wait)", IO_COLOR, 120, curr_y+20, leg_s)
	draw_legend_diamond(ctx, "Runnable threads", PROCS_RUNNING_COLOR,
			120 +90, curr_y+20, leg_s, leg_s)
	draw_legend_diamond(ctx, "Blocked threads -- Uninterruptible Syscall", PROCS_BLOCKED_COLOR,
			120 +90 +140, curr_y+20, leg_s, leg_s)

	chart_rect = (0, curr_y+30, w, bar_h)
	if clip_visible (clip, chart_rect):
		draw_box_ticks (ctx, chart_rect)
		draw_annotations (ctx, proc_tree, trace.times, chart_rect)
		# render I/O wait -- a backwards delta
		draw_chart (ctx, IO_COLOR, True, chart_rect, \
			    [(sample.time, sample.user + sample.sys + sample.io) for sample in trace.cpu_stats], \
			    proc_tree, None, plot_square)
		# render CPU load -- a backwards delta
		draw_chart (ctx, CPU_COLOR, True, chart_rect, \
			    [(sample.time, sample.user + sample.sys) for sample in trace.cpu_stats], \
			    proc_tree, None, plot_square)

		# instantaneous sample
		draw_chart (ctx, PROCS_RUNNING_COLOR, False, chart_rect,
			    [(sample.time, sample.procs_running) for sample in trace.cpu_stats], \
			    proc_tree, [0, 9], plot_scatter_positive)

		# instantaneous sample
		draw_chart (ctx, PROCS_BLOCKED_COLOR, False, chart_rect,
			    [(sample.time, sample.procs_blocked) for sample in trace.cpu_stats], \
			    proc_tree, [0, 9], plot_scatter_positive)

	curr_y = curr_y + 50 + bar_h

	# render second chart
	draw_legend_box(ctx, "Disk utilization -- fraction of sample interval I/O queue was not empty",
			IO_COLOR, 0, curr_y+20, leg_s)
	if OPTIONS.show_ops_not_bytes:
		unit = "ops"
	else:
		unit = "bytes"
	draw_legend_line(ctx, "Disk writes -- " + unit + "/sample",
			 DISK_WRITE_COLOR, 470, curr_y+20, leg_s)
	draw_legend_line(ctx, "Disk reads+writes -- " + unit + "/sample",
			 DISK_TPUT_COLOR, 470+120*2, curr_y+20, leg_s)

	curr_y += 5

	# render disk throughput
	max_sample = None

        # render I/O utilization
	for partition in trace.disk_stats:
		draw_text(ctx, partition.name, TEXT_COLOR, 0, curr_y+30)

		# utilization -- inherently normalized [0,1]
		chart_rect = (0, curr_y+30+5, w, bar_h)
		if clip_visible (clip, chart_rect):
			draw_box_ticks (ctx, chart_rect)
			draw_annotations (ctx, proc_tree, trace.times, chart_rect)
			# a backwards delta
			draw_chart (ctx, IO_COLOR, True, chart_rect,
					    [(sample.time, sample.util) for sample in partition.samples],
					    proc_tree, [0, 1], plot_square)

		# render disk throughput
		#  XXX assume single block device, for now
		if not max_sample:
			#  XXX correction for non-constant sample.time?
			max_sample = max (partition.samples, key = lambda s: s.tput)
		if clip_visible (clip, chart_rect):
			# a backwards delta
			draw_chart (ctx, DISK_TPUT_COLOR, False, chart_rect,
					    [(sample.time, sample.tput) for sample in partition.samples],
					    proc_tree, [0, max_sample.tput], plot_segment_positive)

			# overlay write throughput
			# a backwards delta
			draw_chart (ctx, DISK_WRITE_COLOR, False, chart_rect,
					    [(sample.time, sample.write) for sample in partition.samples],
					    proc_tree, [0, max_sample.tput], plot_segment_positive)

		# pos_x = ((max_sample.time - proc_tree.start_time) * w / proc_tree.duration())
		#
		# shift_x, shift_y = -20, 20
		# if (pos_x < 245):
		# 	shift_x, shift_y = 5, 40
		#
		# DISK_BLOCK_SIZE = 1024
		# label = "%.1fMB/s" % round ((max_sample.tput) / DISK_BLOCK_SIZE)
		# draw_text (ctx, label, DISK_TPUT_COLOR, pos_x + shift_x, curr_y + shift_y)

		curr_y = curr_y + 30 + bar_h

	# render mem usage
	chart_rect = (0, curr_y+30, w, meminfo_bar_h)
	mem_stats = trace.mem_stats
	if mem_stats and clip_visible (clip, chart_rect):
		mem_scale = max(sample.records['MemTotal'] - sample.records['MemFree'] for sample in mem_stats)
		draw_legend_box(ctx, "Mem cached (scale: %u MiB)" % (float(mem_scale) / 1024), MEM_CACHED_COLOR, curr_y+20, leg_s)
		draw_legend_box(ctx, "Used", MEM_USED_COLOR, 240, curr_y+20, leg_s)
		draw_legend_box(ctx, "Buffers", MEM_BUFFERS_COLOR, 360, curr_y+20, leg_s)
		draw_legend_line(ctx, "Swap (scale: %u MiB)" % max([(sample.records['SwapTotal'] - sample.records['SwapFree'])/1024 for sample in mem_stats]), \
				 MEM_SWAP_COLOR, 480, curr_y+20, leg_s)
		draw_box_ticks(ctx, chart_rect)
		draw_annotations(ctx, proc_tree, trace.times, chart_rect)
		draw_chart(ctx, MEM_BUFFERS_COLOR, True, chart_rect, \
			   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree']) for sample in trace.mem_stats], \
			   proc_tree, [0, mem_scale], plot_square)
		draw_chart(ctx, MEM_USED_COLOR, True, chart_rect, \
			   [(sample.time, sample.records['MemTotal'] - sample.records['MemFree'] - sample.records['Buffers']) for sample in mem_stats], \
			   proc_tree, [0, mem_scale], plot_square)
		draw_chart(ctx, MEM_CACHED_COLOR, True, chart_rect, \
			   [(sample.time, sample.records['Cached']) for sample in mem_stats], \
			   proc_tree, [0, mem_scale], plot_square)
		draw_chart(ctx, MEM_SWAP_COLOR, False, chart_rect, \
			   [(sample.time, float(sample.records['SwapTotal'] - sample.records['SwapFree'])) for sample in mem_stats], \
			   proc_tree, None, plot_square)

		curr_y = curr_y + meminfo_bar_h

	return curr_y

ISOTEMPORAL_CSEC = None

#
# Render the chart.
#
# "ctx" is the Cairo drawing context.  ctx transform already has panning translation
# and "zoom" scaling applied, but not the asymmetrical xscale arg.
def render(ctx, options, xscale, trace, isotemporal_csec = None):
	(w, h) = extents (options, xscale, trace)  # XX  redundant?

	ctx.set_line_width(1.0)
	ctx.select_font_face(FONT_NAME)
	draw_fill_rect(ctx, WHITE, (0, 0, max(w, MIN_IMG_W), h))

	global ISOTEMPORAL_CSEC
	ISOTEMPORAL_CSEC = isotemporal_csec

	ctx.save()
	ctx.translate(off_x, 0)  # current window-coord clip shrinks with loss of the off_x-wide strip on left

	proc_tree = options.proc_tree (trace)

	ctx.new_path()
	ctx.rectangle(0, 0, w, h)
	ctx.clip()

	# x, y, w, h
	clip = (-1, -1, -1, -1) # ctx.clip_extents()

	w -= 2*off_x

	# draw the title and headers
	if proc_tree.idle:
		duration = proc_tree.idle
	else:
		duration = proc_tree.duration()

	if not options.kernel_only:
		curr_y = draw_header (ctx, trace.headers, duration)
	else:
		curr_y = off_y;

	if options.charts:
		curr_y = render_charts (ctx, options, clip, trace, curr_y, w, h)

	# draw process boxes
	proc_height = h
	if proc_tree.taskstats and options.cumulative:
		proc_height -= CUML_HEIGHT

	draw_process_bar_chart(ctx, clip, options, proc_tree, trace.times,
			       curr_y, w, proc_height)

	curr_y = proc_height

	# draw a cumulative CPU-time-per-process graph
	if proc_tree.taskstats and options.cumulative:
		cuml_rect = (0, curr_y + off_y, w, CUML_HEIGHT/2 - off_y * 2)
		if clip_visible (clip, cuml_rect):
			draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_CPU)

	# draw a cumulative I/O-time-per-process graph
	if proc_tree.taskstats and options.cumulative:
		cuml_rect = (0, curr_y + off_y * 100, w, CUML_HEIGHT/2 - off_y * 2)
		if clip_visible (clip, cuml_rect):
			draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_IO)

	if isotemporal_csec:
		draw_isotemporal(ctx, isotemporal_csec)

	ctx.restore()

def draw_isotemporal(ctx, isotemporal_csec):
	ctx.set_source_rgba(0.0, 0.0, 0.0, 1.0)
	ctx.set_line_width(0.8)
	ctx.set_dash([4, 2])
	isotemporal_x = csec_to_xscaled(isotemporal_csec)
	ctx.move_to(isotemporal_x, 0)
	ctx.line_to(isotemporal_x, CUML_HEIGHT)
	ctx.stroke()

def draw_process_bar_chart(ctx, clip, options, proc_tree, times, curr_y, w, h):
	header_size = 0
	if not options.kernel_only:
		draw_legend_diamond (ctx, "Runnable",
				 PROCS_RUNNING_COLOR, 10, curr_y + 45, leg_s*3/4, proc_h)
		draw_legend_diamond (ctx, "Uninterruptible Syscall",
				 PROC_COLOR_D, 10+100, curr_y + 45, leg_s*3/4, proc_h)
		draw_legend_box (ctx, "Running (%cpu)",
				 PROC_COLOR_R, 10+100+180, curr_y + 45, leg_s)
		draw_legend_box (ctx, "Sleeping",
				 PROC_COLOR_S, 10+100+180+130, curr_y + 45, leg_s)
		draw_legend_box (ctx, "Zombie",
				 PROC_COLOR_Z, 10+100+180+130+90, curr_y + 45, leg_s)
		header_size = 45

	#chart_rect = [0, curr_y + header_size + 30,
	#	      w, h - 2 * off_y - (curr_y + header_size + 15) + proc_h]
	chart_rect = [-1, -1, -1, -1]
	ctx.set_font_size (PROC_TEXT_FONT_SIZE)

	draw_box_ticks (ctx, chart_rect)
	if SEC_W > 100:
		nsec = 1
	else:
		nsec = 5
	#draw_sec_labels (ctx, chart_rect, nsec)
	draw_annotations (ctx, proc_tree, times, chart_rect)

	y = curr_y + 60
	for root in proc_tree.process_tree:
		draw_processes_recursively(ctx, root, proc_tree, y, proc_h, chart_rect, clip)
		y = y + proc_h * proc_tree.num_nodes([root])


def draw_header (ctx, headers, duration):
    toshow = [
      ('system.uname', 'uname', lambda s: s),
      ('system.release', 'release', lambda s: s),
      ('system.cpu', 'CPU', lambda s: re.sub('model name\s*:\s*', '', s, 1)),
      ('system.kernel.options', 'kernel options', lambda s: s),
    ]

    header_y = ctx.font_extents()[2] + 10
    ctx.set_font_size(TITLE_FONT_SIZE)
    draw_text(ctx, headers['title'], TEXT_COLOR, 0, header_y)
    ctx.set_font_size(TEXT_FONT_SIZE)

    for (headerkey, headertitle, mangle) in toshow:
        header_y += ctx.font_extents()[2]
        if headerkey in headers:
            value = headers.get(headerkey)
        else:
            value = ""
        txt = headertitle + ': ' + mangle(value)
        draw_text(ctx, txt, TEXT_COLOR, 0, header_y)

#     dur = duration / 100.0
#     txt = 'time : %02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60))
#     if headers.get('system.maxpid') is not None:
#         txt = txt + '      max pid: %s' % (headers.get('system.maxpid'))
#
#    header_y += ctx.font_extents()[2]
#    draw_text (ctx, txt, TEXT_COLOR, 0, header_y)

    return header_y

def draw_processes_recursively(ctx, proc, proc_tree, y, proc_h, rect, clip) :
	x = csec_to_xscaled(proc.start_time)
	w = csec_to_xscaled(proc.start_time + proc.duration) - x  # XX parser fudges duration upward

	draw_process_activity_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip)

	# Do not draw right-hand vertical border -- process exit never exactly known
	ctx.set_source_rgba(*PROC_BORDER_COLOR)
	ctx.set_line_width(1.0)
	ctx.move_to(x+w, y)
	ctx.rel_line_to(-w, 0)
	ctx.rel_line_to(0, proc_h)
	ctx.rel_line_to(w, 0)
	ctx.stroke()

	draw_process_state_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip)

	# Event ticks step on the rectangle painted by draw_process_state_colors() (e.g. for non-interruptible wait);
	# user can work around this by toggling off the event ticks.
	if not OPTIONS.hide_events:
		draw_process_events(ctx, proc, proc_tree, x, y, proc_h, rect)

	ipid = int(proc.pid)
	if proc_tree.taskstats and OPTIONS.show_all:
		cmdString = ''
	else:
		cmdString = proc.cmd
	if (OPTIONS.show_pid or OPTIONS.show_all) and ipid is not 0:
		cmdString = cmdString + " [" + str(ipid / 1000) + "]"
	if OPTIONS.show_all:
		if proc.args:
			cmdString = cmdString + " '" + "' '".join(proc.args) + "'"
		else:
			cmdString = cmdString

	draw_label_in_box(ctx, PROC_TEXT_COLOR, cmdString, x, y + proc_h - 4, w,
			  ctx.clip_extents()[0], ctx.clip_extents()[2])

	next_y = y + proc_h
	for child in proc.child_list:
		child_x, child_y = draw_processes_recursively(ctx, child, proc_tree, next_y, proc_h, rect, clip)
		draw_process_connecting_lines(ctx, x, y, child_x, child_y, proc_h)
		next_y = next_y + proc_h * proc_tree.num_nodes([child])

	return x, y

def draw_process_activity_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip):
	draw_fill_rect(ctx, PROC_COLOR_S, (x, y, w, proc_h))
	if len(proc.samples) <= 0:
		return
	# cases:
	#    1. proc started before sampling did
	#          XX  should look up time of previous sample, not assume 'proc_tree.sample_period'
	#    2. proc start after sampling
	last_time = max(proc.start_time, proc.samples[0].time - proc_tree.sample_period)
	ctx_save__csec_to_xscaled(ctx)
	for sample in proc.samples[1:] :
		alpha = min(sample.cpu_sample.user + sample.cpu_sample.sys, 1.0)  # XX rationale?
 		cpu_color = tuple(list(PROC_COLOR_R[0:3]) + [alpha])
		# XXX  correct color for non-uniform sample intervals
		draw_fill_rect(ctx, cpu_color, (last_time, y, sample.time - last_time, proc_h))
		last_time = sample.time
	ctx.restore()

def draw_process_events(ctx, proc, proc_tree, x, y, proc_h, rect):
	ev_regex = re.compile(OPTIONS.event_regex)
	if ISOTEMPORAL_CSEC:
		time_origin_relative = ISOTEMPORAL_CSEC
	else:
		time_origin_relative = time_origin_drawn + proc_tree.sample_period  # XX align to time of first sample
	ctx.set_source_rgba(*EVENT_COLOR)
	last_x_touched = 0
	last_label_str = None
	precision = int( min(6, SEC_W/100))
	for ev in proc.events:
		if not ev_regex.match(ev.match) and ev.match != "sample_start":
			continue
		tx = csec_to_xscaled(ev.time)
		ctx.move_to(tx-1, y+proc_h)
		ctx.line_to(tx,   y+proc_h-5)
		ctx.line_to(tx+1, y+proc_h)
		ctx.line_to(tx,   y+proc_h)
		ctx.fill()
		if OPTIONS.print_event_times and tx > last_x_touched + 5:
			label_str = '%.*f' % (precision, (float(ev.time_usec)/1000/10 - time_origin_relative) / CSEC)
			if label_str != last_label_str:
				last_x_touched = tx + draw_label_in_box_at_time(
				ctx, PROC_TEXT_COLOR,
				label_str,
				y + proc_h - 4, tx)
				last_label_str = label_str

def draw_process_state_colors(ctx, proc, proc_tree, x, y, w, proc_h, rect, clip):
	last_tx = -1
	for sample in proc.samples :
		tx = csec_to_xscaled(sample.time)
		state = get_proc_state( sample.state )
		if state == STATE_WAITING or state == STATE_RUNNING:
			color = STATE_COLORS[state]
			ctx.set_source_rgba(*color)
			draw_diamond(ctx, tx, y + proc_h/2, 2.5, proc_h)

def draw_process_connecting_lines(ctx, px, py, x, y, proc_h):
	ctx.set_source_rgba(*DEP_COLOR)
	ctx.set_dash([2, 2])
	if abs(px - x) < 3:
		dep_off_x = 3
		dep_off_y = proc_h / 4
		ctx.move_to(x, y + proc_h / 2)
		ctx.line_to(px - dep_off_x, y + proc_h / 2)
		ctx.line_to(px - dep_off_x, py - dep_off_y)
		ctx.line_to(px, py - dep_off_y)
	else:
		ctx.move_to(x, y + proc_h / 2)
		ctx.line_to(px, y + proc_h / 2)
		ctx.line_to(px, py)
	ctx.stroke()
	ctx.set_dash([])

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

# taskstats-specific
def draw_cuml_graph(ctx, proc_tree, chart_bounds, duration, stat_type):
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
#	print "total time: %g pix-per-ns %g" % (total_time, pix_per_ns)

	# FIXME: we have duplicates in the process list too [!] - why !?

	# Render bottom up, left to right
	below = {}
	for time in times:
		below[time] = chart_bounds[1] + chart_bounds[3]

	# same colors each time we render
	random.seed (0)

	ctx.set_line_width(1)

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

		last_time = times[0]
		y = last_below = below[last_time]
		last_cuml = cuml = 0.0

		ctx.set_source_rgba(*cs.get_color())
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

#			if last_cuml > cuml:
#				assert fail ... - un-sorted process samples

			# draw the trailing rectangle from the last time to
			# before now, at the height of the last segment.
			if render_seg:
				w = math.ceil ((time - last_time) * chart_bounds[2] / proc_tree.duration()) + 1
				x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration())
				ctx.rectangle (x, below[last_time] - last_cuml, w, last_cuml)
				ctx.fill()
#				ctx.stroke()
				last_time = time
				y = below [time] - cuml

			row[time] = y

		# render the last segment
		x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration())
		y = below[last_time] - cuml
		ctx.rectangle (x, y, chart_bounds[2] - x, cuml)
		ctx.fill()
#		ctx.stroke()

		# render legend if it will fit
		if cuml > 8:
			label = cs.cmd
			extnts = ctx.text_extents(label)
			label_w = extnts[2]
			label_h = extnts[3]
#			print "Text extents %g by %g" % (label_w, label_h)
			labels.append((label,
				       chart_bounds[0] + chart_bounds[2] - label_w,
				       y + (cuml + label_h) / 2))
			if cs in legends:
				print("ARGH - duplicate process in list !")

		legends.append ((cs, process_total_time))

		below = row

	# render grid-lines over the top
	draw_box_ticks(ctx, chart_bounds)

	# render labels
	for l in labels:
		draw_text(ctx, l[0], TEXT_COLOR, l[1], l[2])

	# Render legends
	font_height = 20
	label_width = 300
	LEGENDS_PER_COL = 15
	LEGENDS_TOTAL = 45
	ctx.set_font_size (TITLE_FONT_SIZE)
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

	draw_text(ctx, label, TEXT_COLOR, chart_bounds[0],
		  chart_bounds[1] + font_height)

	i = 0
	legends.sort(lambda a, b: cmp (b[1], a[1]))
	ctx.set_font_size(TEXT_FONT_SIZE)
	for t in legends:
		cs = t[0]
		time = t[1]
		x = chart_bounds[0] + int (i/LEGENDS_PER_COL) * label_width
		y = chart_bounds[1] + font_height * ((i % LEGENDS_PER_COL) + 2)
		str = "%s - %.0f(ms) (%2.2f%%)" % (cs.cmd, time/1000000, (time/total_time) * 100.0)
		draw_legend_box(ctx, str, cs.color, x, y, leg_s)
		i = i + 1
		if i >= LEGENDS_TOTAL:
			break
