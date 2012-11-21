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

import sys
import cairo
import math
import re
import random
import colorsys
import traceback
import collections

# Constants: Put the more heavily used, non-derived constants in a named tuple, for immutability.
# XX  The syntax is awkward, but more elegant alternatives have run-time overhead.
#     http://stackoverflow.com/questions/4996815/ways-to-make-a-class-immutable-in-python
DrawConsts = collections.namedtuple('XXtypename',
            ['CSEC','bar_h','off_x','off_y','proc_h','leg_s','CUML_HEIGHT','MIN_IMG_W'])
C = DrawConsts( 100,     55,     10,     10,      16,     11,         2000,        800)
#                                                 height of a process, in user-space

# Derived constants
#   XX  create another namedtuple for these
meminfo_bar_h = 2 * C.bar_h

# Process tree background color.
BACK_COLOR = (1.0, 1.0, 1.0, 1.0)

WHITE = (1.0, 1.0, 1.0, 1.0)
NOTEPAD_YELLLOW = (0.95, 0.95, 0.8, 1.0)
PURPLE = (0.6, 0.1, 0.6, 1.0)

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
MAGENTA = (0.7, 0.0, 0.7, 1.0)
DISK_WRITE_COLOR = MAGENTA
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
DIM_EVENT_COLOR =       (0.3, 0.3, 0.3)
EVENT_COLOR =           (0.1, 0.1, 0.1)
HIGHLIGHT_EVENT_COLOR = (2.0, 0.0, 4.0)

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
JUSTIFY_CENTER = "center"

# CumulativeStats Types
STAT_TYPE_CPU = 0
STAT_TYPE_IO = 1

# Convert ps process state to an int
def get_proc_state(flag):
	return "RSDTZXW".find(flag) + 1

def draw_text(cr, text, color, x, y):
	cr.set_source_rgba(*color)
	cr.move_to(x, y)
	cr.show_text(text)

def draw_fill_rect(cr, color, rect):
	cr.set_source_rgba(*color)
	cr.rectangle(*rect)
	cr.fill()

def draw_rect(cr, color, rect):
	cr.set_source_rgba(*color)
	cr.rectangle(*rect)
	cr.stroke()

def draw_diamond(cr, x, y, w, h):
	cr.save()
	cr.set_line_width(0.0)
	cr.move_to(x-w/2, y)
	cr.line_to(x, y+h/2)
	cr.line_to(x+w/2, y)
	cr.line_to(x, y-h/2)
	cr.line_to(x-w/2, y)
	cr.fill()
	cr.restore()

def draw_legend_diamond(cr, label, fill_color, x, y, w, h):
	cr.set_source_rgba(*fill_color)
	draw_diamond(cr, x, y-h/2, w, h)
	draw_text(cr, label, TEXT_COLOR, x + w + 5, y)

def draw_legend_box(cr, label, fill_color, x, y, s):
	draw_fill_rect(cr, fill_color, (x, y - s, s, s))
	#draw_rect(cr, PROC_BORDER_COLOR, (x, y - s, s, s))
	draw_text(cr, label, TEXT_COLOR, x + s + 5, y)

def draw_legend_line(cr, label, fill_color, x, y, s):
	draw_fill_rect(cr, fill_color, (x, y - s/2, s + 1, 3))
	cr.fill()
	draw_text(cr, label, TEXT_COLOR, x + s + 5, y)

def draw_label_in_box_at_time(cr, color, label, y, label_x):
	draw_text(cr, label, color, label_x, y)
	return cr.text_extents(label)[2]


def _time_origin_drawn(ctx, trace):
	if ctx.app_options.prehistory:
		# XX  Would have to set to proc_tree.starttime for backwards compatibility
		return 0
	else:
		return trace.cpu_stats[0].time - in_chart_X_margin(ctx.proc_tree(trace))

def _sec_w(xscale):
	return xscale * 50 # width of a second, in user-space

# XX  Migrating functions into the drawing object seems to be a loss: the
# replacement of 'ctx' with 'self' is no help to the reader, and
# additional text columns are lost to the necessary indentation
class DrawContext:
	'''set all drawing-related variables bindable at time of class PyBootchartWindow instantiation'''
	def __init__(self, app_options, trace, cumulative = True, charts = True, kernel_only = False):
		self.app_options = app_options
		# should we render a cumulative CPU time chart
		self.cumulative = cumulative  # Bootchart2 collector only
		self.charts = charts
		self.kernel_only = kernel_only  # set iff collector daemon saved output of `dmesg`
		self.SWEEP_CSEC = None
		self.event_dump_list = None

		self.cr = None                # Cairo rendering context
		self.time_origin_drawn = None # time of leftmost plotted data, as integer csecs
		self.SEC_W = None

		# per-rendering state
		self.proc_above_was_hidden = False

	def per_render_init(self, cr, time_origin_drawn, SEC_W):
		self.cr = cr
		self.time_origin_drawn = time_origin_drawn
		self.SEC_W = SEC_W
		self.highlight_event__func_file_line_RE = re.compile(self.app_options.event_regex)

	def proc_tree (self, trace):
		return trace.kernel_tree if self.kernel_only else trace.proc_tree

	def draw_label_in_box(self, color, label,
			      x, y, w, minx, maxx):
		# hack in a pair of left and right margins
		extents = self.cr.text_extents("j" + label + "k")   # XX  "j", "k" were found by tedious trial-and-error
		label = " " + label

		label_y_bearing = extents[1]
		label_w = extents[2]
		label_height = extents[3]
		label_y_advance = extents[5]

		y += C.proc_h
		if self.app_options.justify == JUSTIFY_CENTER and label_w + 10 <= w:
			label_x = x + w / 2 - label_w / 2   # CENTER
		else:
			label_x = x - label_w - 2
		if label_x < minx:
			label_x = minx
		# XX ugly magic constants, tuned by trial-and-error
		draw_fill_rect(self.cr, NOTEPAD_YELLLOW, (label_x, y-1, label_w, -(C.proc_h-2)))
		draw_text(self.cr, label, color, label_x, y-4)

# XX  Should be "_csec_to_user"
# Assume off_x translation is already applied, as it will be in drawing functions.
def _csec_to_xscaled(t_csec, time_origin_drawn, sec_w):
	return (t_csec-time_origin_drawn) * sec_w / C.CSEC

def csec_to_xscaled(ctx, t_csec):
	return _csec_to_xscaled(t_csec, ctx.time_origin_drawn, ctx.SEC_W)

# Solve for t_csec:
#   x = (t_csec-ctx.time_origin_drawn) * ctx.SEC_W / C.CSEC + C.off_x
#
#   x - C.off_x = (t_csec-ctx.time_origin_drawn) * ctx.SEC_W / C.CSEC
#   (x - C.off_x) * C.CSEC / ctx.SEC_W = t_csec-ctx.time_origin_drawn
#
def xscaled_to_csec(ctx, x):
	return _xscaled_to_csec(x, ctx.SEC_W, ctx.time_origin_drawn)

# XX  Prefix with single underbar '_' -- double underbar '__' has special meaning to Python
#     that precludes use in exported functions.
def _xscaled_to_csec(x, sec_w, _time_origin_drawn):
	return (x - C.off_x) * C.CSEC / sec_w + _time_origin_drawn

def ctx_save__csec_to_xscaled(ctx):
	ctx.cr.save()
	ctx.cr.scale(float(ctx.SEC_W) / C.CSEC, 1.0)
	ctx.cr.translate(-ctx.time_origin_drawn, 0.0)

def draw_sec_labels(ctx, rect, nsecs):
	ctx.cr.set_font_size(AXIS_FONT_SIZE)
	prev_x = 0
	for i in range(0, rect[2] + 1, ctx.SEC_W):
		if ((i / ctx.SEC_W) % nsecs == 0) :
			label = "%ds" % (i / ctx.SEC_W)
			label_w = ctx.cr.text_extents(label)[2]
			x = rect[0] + i - label_w/2
			if x >= prev_x:
				draw_text(ctx.cr, label, TEXT_COLOR, x, rect[1] - 2)
				prev_x = x + label_w

def draw_box(ctx, rect):
	draw_rect(ctx.cr, BORDER_COLOR, tuple(rect))

def draw_annotations(ctx, proc_tree, times, rect):
    ctx.cr.set_line_cap(cairo.LINE_CAP_SQUARE)
    ctx.cr.set_source_rgba(*ANNOTATION_COLOR)
    ctx.cr.set_dash([4, 4])

    for time in times:
        if time is not None:
            x = csec_to_xscaled(ctx, time)

            ctx.cr.move_to(x, rect[1] + 1)
            ctx.cr.line_to(x, rect[1] + rect[3] - 1)
            ctx.cr.stroke()

    ctx.cr.set_line_cap(cairo.LINE_CAP_BUTT)
    ctx.cr.set_dash([])

def plot_line(cr, point, x, y):
	cr.set_line_width(1.0)
	cr.line_to(x, y)       # rightward, and upward or downward

# backward-looking
def plot_square(cr, point, x, y):
	cr.set_line_width(1.0)
        cr.line_to(cr.get_current_point()[0], y)  # upward or downward
        cr.line_to(x, y)  # rightward

# backward-looking
def plot_segment_positive(cr, point, x, y):
	cr.move_to(cr.get_current_point()[0], y)       # upward or downward
	if point[1] <= 0:           # zero-Y samples draw nothing
		cr.move_to(x, y)
		return
	cr.set_line_width(1.5)
	cr.line_to(x, y)

def _plot_scatter_positive(cr, point, x, y, w, h):
	if point[1] <= 0:
		return
	draw_diamond(cr, x, y, w, h)

def plot_scatter_positive_big(cr, point, x, y):
	return _plot_scatter_positive(cr, point, x, y, 5.5, 5.5)

def plot_scatter_positive_small(cr, point, x, y):
	return _plot_scatter_positive(cr, point, x, y, 3.6, 3.6)

# All charts assumed to be full-width
def draw_chart(ctx, color, fill, chart_bounds, data, proc_tree, data_range, plot_point_func):
	def transform_point_coords(point, y_base, yscale):
		x = csec_to_xscaled(ctx, point[0])
		y = (point[1] - y_base) * -yscale + chart_bounds[1] + chart_bounds[3]
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

	ctx.cr.set_source_rgba(*color)

	# move to the x of the missing first sample point
	first = transform_point_coords ([ctx.time_origin_drawn + in_chart_X_margin(proc_tree), -9999],
					ybase, yscale)
	ctx.cr.move_to(first[0], first[1])

	for point in data:
		x, y = transform_point_coords (point, ybase, yscale)
		plot_point_func(ctx.cr, point, x, y)

	final = transform_point_coords (data[-1], ybase, yscale)

	if fill:
		ctx.cr.set_line_width(0.0)
		ctx.cr.stroke_preserve()
		ctx.cr.line_to(final[0], chart_bounds[1]+chart_bounds[3])
		ctx.cr.line_to(first[0], chart_bounds[1]+chart_bounds[3])
		ctx.cr.line_to(first[0], first[1])
		ctx.cr.fill()
	else:
		ctx.cr.stroke()
	ctx.cr.set_line_width(1.0)

def in_chart_X_margin(proc_tree):
	return proc_tree.sample_period

# A _pure_ function of its arguments -- writes to no global state nor object.
# Called from gui.py and batch.py, before instantiation of
# DrawContext and first call to render(), then every time xscale
# changes.
# Returned (w, h) maximum useful x, y user coordinates -- minimums are 0, 0.
# (w) will get bigger if xscale does.
def extents(ctx, xscale, trace):
	'''arg "options" is a RenderOptions object'''
	proc_tree = ctx.proc_tree(trace)

	w = int (_csec_to_xscaled(trace.cpu_stats[-1].time + in_chart_X_margin(proc_tree),
				   _time_origin_drawn(ctx, trace),
				   _sec_w(xscale)) \
		 + 2*C.off_x)

	h = C.proc_h * proc_tree.num_proc + 2 * C.off_y
	if ctx.charts:
		h += 110 + (2 + len(trace.disk_stats)) * (30 + C.bar_h) + 1 * (30 + meminfo_bar_h)
	if proc_tree.taskstats and ctx.cumulative:
		h += C.CUML_HEIGHT + 4 * C.off_y
	return (w, h)  # includes C.off_x, C.off_y

def render_charts(ctx, trace, curr_y, w, h):
	proc_tree = ctx.proc_tree(trace)

	if ctx.app_options.show_legends:
		# render bar legend
		ctx.cr.set_font_size(LEGEND_FONT_SIZE)
		curr_y += 20
		draw_legend_box(ctx.cr, "CPU (user+sys)", CPU_COLOR, 0, curr_y, C.leg_s)
		draw_legend_box(ctx.cr, "I/O (wait)", IO_COLOR, 120, curr_y, C.leg_s)
		draw_legend_diamond(ctx.cr, "Runnable threads", PROCS_RUNNING_COLOR,
				    120 +90, curr_y, C.leg_s, C.leg_s)
		draw_legend_diamond(ctx.cr, "Blocked threads -- Uninterruptible Syscall", PROCS_BLOCKED_COLOR,
				    120 +90 +140, curr_y, C.leg_s, C.leg_s)

	chart_rect = (0, curr_y+10, w, C.bar_h)
	draw_box (ctx, chart_rect)
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
	draw_chart (ctx, PROCS_BLOCKED_COLOR, False, chart_rect,
		    [(sample.time, sample.procs_blocked) for sample in trace.cpu_stats], \
		    proc_tree, [0, 9], plot_scatter_positive_big)

	# instantaneous sample
	draw_chart (ctx, PROCS_RUNNING_COLOR, False, chart_rect,
		    [(sample.time, sample.procs_running) for sample in trace.cpu_stats], \
		    proc_tree, [0, 9], plot_scatter_positive_small)

	curr_y += 8 + C.bar_h

	if ctx.app_options.show_legends:
		curr_y += 30
		# render second chart
		draw_legend_box(ctx.cr, "Disk utilization -- fraction of sample interval I/O queue was not empty",
				IO_COLOR, 0, curr_y, C.leg_s)
		if ctx.app_options.show_ops_not_bytes:
			unit = "ops"
		else:
			unit = "bytes"
		draw_legend_line(ctx.cr, "Disk writes -- " + unit + "/sample",
				 DISK_WRITE_COLOR, 470, curr_y, C.leg_s)
		draw_legend_line(ctx.cr, "Disk reads+writes -- " + unit + "/sample",
				 DISK_TPUT_COLOR, 470+120*2, curr_y, C.leg_s)

	# render disk throughput
	max_sample = None

        # render I/O utilization
	for partition in trace.disk_stats:
		draw_text(ctx.cr, partition.name, TEXT_COLOR, 0, curr_y+18)

		# utilization -- inherently normalized [0,1]
		chart_rect = (0, curr_y+18+5, w, C.bar_h)
		draw_box (ctx, chart_rect)
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

		curr_y += 18+C.bar_h

	# render mem usage
	chart_rect = (0, curr_y+30, w, meminfo_bar_h)
	mem_stats = trace.mem_stats
	if mem_stats:
		mem_scale = max(sample.records['MemTotal'] - sample.records['MemFree'] for sample in mem_stats)
		if ctx.app_options.show_legends:
			curr_y += 20
			draw_legend_box(ctx.cr, "Mem cached (scale: %u MiB)" % (float(mem_scale) / 1024), MEM_CACHED_COLOR, curr_y, C.leg_s)
			draw_legend_box(ctx.cr, "Used", MEM_USED_COLOR, 240, curr_y, C.leg_s)
			draw_legend_box(ctx.cr, "Buffers", MEM_BUFFERS_COLOR, 360, curr_y, C.leg_s)
			draw_legend_line(ctx.cr, "Swap (scale: %u MiB)" % max([(sample.records['SwapTotal'] - sample.records['SwapFree'])/1024 for sample in mem_stats]), \
					 MEM_SWAP_COLOR, 480, curr_y, C.leg_s)
		draw_box (ctx, chart_rect)
		draw_annotations (ctx, proc_tree, trace.times, chart_rect)
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

def late_init_transform(cr):
	cr.translate(C.off_x, 0)  # current window-coord clip shrinks with loss of the C.off_x-wide strip on left

#
# Render the chart.  Central method of this module.
#
def render(cr, ctx, xscale, trace, sweep_csec = None, hide_process_y = None):
        '''
	"cr" is the Cairo drawing context -- the transform matrix it carries already has
	 panning translation and "zoom" scaling applied.
	 The asymmetrical "xscale" arg is not applied globally to "cr", because
	 it would distort letterforms of text output.
	"ctx" is a DrawContext object.
	'''
	#traceback.print_stack()
	(w, h) = extents(ctx, xscale, trace)

	ctx.per_render_init(cr, _time_origin_drawn(ctx, trace), _sec_w(xscale))
	ctx.SWEEP_CSEC = sweep_csec

	ctx.cr.set_line_width(1.0)
	ctx.cr.select_font_face(FONT_NAME)
	draw_fill_rect(ctx.cr, WHITE, (0, 0, max(w, C.MIN_IMG_W), h))

	ctx.cr.save()
	late_init_transform(ctx.cr)

	proc_tree = ctx.proc_tree (trace)

	# draw the title and headers
	if proc_tree.idle:
		duration = proc_tree.idle
	else:
		duration = proc_tree.duration()

	if not ctx.kernel_only:
		curr_y = draw_header (ctx, trace.headers, duration)
	else:
		curr_y = C.off_y;

	w -= 2*C.off_x
	if ctx.charts:
		curr_y = render_charts (ctx, trace, curr_y, w, h)

	# draw process boxes
	proc_height = h
	if proc_tree.taskstats and ctx.cumulative:
		proc_height -= C.CUML_HEIGHT

	ctx.hide_process_y = hide_process_y
	draw_process_bar_chart(ctx, proc_tree, trace.times,
			       curr_y, w, proc_height)

	curr_y = proc_height

	# draw a cumulative CPU-time-per-process graph
	if proc_tree.taskstats and ctx.cumulative:
		cuml_rect = (0, curr_y + C.off_y, w, C.CUML_HEIGHT/2 - C.off_y * 2)
		draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_CPU)

	# draw a cumulative I/O-time-per-process graph
	if proc_tree.taskstats and ctx.cumulative:
		cuml_rect = (0, curr_y + C.off_y * 100, w, C.CUML_HEIGHT/2 - C.off_y * 2)
		draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_IO)

	if sweep_csec:
		draw_sweep(ctx, sweep_csec[0], sweep_csec[1] - sweep_csec[0])
		#dump_pseudo_event(ctx, "start of event window, width " + int(width*1000) + "msec")

	ctx.cr.restore()

	if ctx.event_dump_list == None:
		return

	print  # blank, separator line
	if ctx.app_options.dump_raw_event_context:
	        # dump all raw log lines between events, where "between" means merely textually,
		# irrespective of time.
		ctx.event_dump_list.sort(key = lambda e: e.raw_log_seek)
		if len(ctx.event_dump_list):
			event0 = ctx.event_dump_list[0]
			event0.raw_log_file.seek(event0.raw_log_seek)
			eventN = ctx.event_dump_list[-1]
			#for line in event0.raw_log_file.readline():
			while event0.raw_log_file.tell() <= eventN.raw_log_seek:
				print event0.raw_log_file.readline(),
	else:   # dump events only
		ctx.event_dump_list.sort(key = lambda ev: ev.time_usec)
		for ev in ctx.event_dump_list:
			print ev.time_usec, ".", ev.raw_log_line(),

	ctx.event_dump_list = None

def draw_sweep(ctx, sweep_csec, width_csec):
	def draw_shading(cr, rect):
		# alpha value of the rgba strikes a compromise between appearance on screen, and in printed screenshot
		cr.set_source_rgba(0.0, 0.0, 0.0, 0.08)
		cr.set_line_width(0.0)
		cr.rectangle(rect)
		cr.fill()
	def draw_vertical(cr, x):
		cr.set_dash([1, 3])
		cr.set_source_rgba(0.0, 0.0, 0.0, 1.0)
		cr.set_line_width(1.0)
		cr.move_to(x, 0)
		cr.line_to(x, height)
		cr.stroke()

	height = int(ctx.cr.device_to_user(0,2000)[1])
	x = csec_to_xscaled(ctx, sweep_csec)
	draw_shading(ctx.cr, (int(x),0,int(ctx.cr.clip_extents()[0]-x),height))
	draw_vertical(ctx.cr, x)

	x = csec_to_xscaled(ctx, sweep_csec + width_csec)
	draw_shading(ctx.cr, (int(x),0,int(ctx.cr.clip_extents()[2]-x),height))
	draw_vertical(ctx.cr, x)

def draw_process_bar_chart(ctx, proc_tree, times, curr_y, w, h):
	if ctx.app_options.show_legends and not ctx.kernel_only:
		curr_y += 30
		draw_legend_diamond (ctx.cr, "Runnable",
				 PROCS_RUNNING_COLOR, 10, curr_y, C.leg_s*3/4, C.proc_h)
		draw_legend_diamond (ctx.cr, "Uninterruptible Syscall",
				 PROC_COLOR_D, 10+100, curr_y, C.leg_s*3/4, C.proc_h)
		draw_legend_box (ctx.cr, "Running (%cpu)",
				 PROC_COLOR_R, 10+100+180, curr_y, C.leg_s)
		draw_legend_box (ctx.cr, "Sleeping",
				 PROC_COLOR_S, 10+100+180+130, curr_y, C.leg_s)
		draw_legend_box (ctx.cr, "Zombie",
				 PROC_COLOR_Z, 10+100+180+130+90, curr_y, C.leg_s)
		curr_y -= 9

	chart_rect = [-1, -1, -1, -1]
	ctx.cr.set_font_size (PROC_TEXT_FONT_SIZE)

	if ctx.SEC_W > 100:
		nsec = 1
	else:
		nsec = 5
	#draw_sec_labels (ctx.cr, chart_rect, nsec)
	draw_annotations (ctx, proc_tree, times, chart_rect)

	curr_y += 15
	for root in proc_tree.process_tree:
		draw_processes_recursively(ctx, root, proc_tree, curr_y)
		curr_y += C.proc_h * proc_tree.num_nodes_drawn([root])
	if ctx.proc_above_was_hidden:
		draw_hidden_process_separator(ctx, curr_y)
		ctx.proc_above_was_hidden = False

def draw_header (ctx, headers, duration):
    toshow = [
      ('system.uname', 'uname', lambda s: s),
      ('system.release', 'release', lambda s: s),
      ('system.cpu', 'CPU', lambda s: re.sub('model name\s*:\s*', '', s, 1)),
      ('system.kernel.options', 'kernel options', lambda s: s),
    ]

    cr = ctx.cr
    header_y = cr.font_extents()[2] + 10
    cr.set_font_size(TITLE_FONT_SIZE)
    draw_text(cr, headers['title'], TEXT_COLOR, 0, header_y)
    cr.set_font_size(TEXT_FONT_SIZE)

    for (headerkey, headertitle, mangle) in toshow:
        header_y += cr.font_extents()[2]
        if headerkey in headers:
            value = headers.get(headerkey)
        else:
            value = ""
        txt = headertitle + ': ' + mangle(value)
        draw_text(cr, txt, TEXT_COLOR, 0, header_y)

#     dur = duration / 100.0
#     txt = 'time : %02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60))
#     if headers.get('system.maxpid') is not None:
#         txt = txt + '      max pid: %s' % (headers.get('system.maxpid'))
#
#    header_y += cr.font_extents()[2]
#    draw_text (cr, txt, TEXT_COLOR, 0, header_y)

    return header_y

def draw_process(ctx, proc, proc_tree, x, y, w):
	draw_process_activity_colors(ctx, proc, proc_tree, x, y, w)

	# Do not draw right-hand vertical border -- process exit never exactly known
	ctx.cr.set_source_rgba(*PROC_BORDER_COLOR)
	ctx.cr.set_line_width(1.0)
	ctx.cr.move_to(x+w, y)
	ctx.cr.rel_line_to(-w, 0)
	if proc.start_time < ctx.time_origin_drawn:
		ctx.cr.stroke()
		ctx.cr.move_to(x, y+C.proc_h)
	else:
		ctx.cr.rel_line_to(0, C.proc_h)
	ctx.cr.rel_line_to(w, 0)
	ctx.cr.stroke()

	draw_process_state_colors(ctx, proc, proc_tree, x, y, w)

	# Event ticks step on the rectangle painted by draw_process_state_colors(),
	# e.g. for non-interruptible wait.
	# User can work around this by toggling off the event ticks.
	if not ctx.app_options.hide_events:
		draw_process_events(ctx, proc, proc_tree, x, y)

	if proc_tree.taskstats and ctx.app_options.show_all:
		cmdString = ''
	else:
		cmdString = proc.cmd
	if (ctx.app_options.show_pid or ctx.app_options.show_all) and proc.pid is not 0:
		prefix = " ["
		if ctx.app_options.show_all:
			prefix += str(proc.ppid / 1000) + ":"
		prefix += str(proc.pid / 1000) + ":" + str(proc.tid / 1000) + "]"
		cmdString = prefix + cmdString
	if ctx.app_options.show_all and proc.args:
		cmdString += " '" + "' '".join(proc.args) + "'"

	ctx.draw_label_in_box( PROC_TEXT_COLOR, cmdString,
			csec_to_xscaled(ctx, max(proc.start_time,ctx.time_origin_drawn)),
			y,
			w,
			ctx.cr.device_to_user(0, 0)[0],
			ctx.cr.clip_extents()[2])

def draw_processes_recursively(ctx, proc, proc_tree, y):
	xmin = ctx.cr.device_to_user(0, 0)[0]   # work around numeric overflow at high xscale factors
	xmin = max(xmin, 0)
	x = max(xmin, csec_to_xscaled(ctx, proc.start_time))
	w = max(xmin, csec_to_xscaled(ctx, proc.start_time + proc.duration)) - x

	if ctx.hide_process_y:
		if ctx.hide_process_y < y - C.proc_h/4:
			ctx.hide_process_y = None       # no further hits in traversal are possible
		else:
			if ctx.hide_process_y < y + C.proc_h/4:
				if not proc.draw:
					proc.draw = True
					ctx.hide_process_y += C.proc_h  # unhide all in consecutive hidden processes
				else:
					pass  # ignore hits on the border region if the process is not hidden
			elif ctx.hide_process_y < y + C.proc_h*3/4:
				if proc.draw:
					proc.draw = False
					ctx.hide_process_y = None
				else:
					pass  # ignore hits on already-hidden processes

	if not proc.draw:
		y -= C.proc_h
		ctx.proc_above_was_hidden = True
	else:
		draw_process(ctx, proc, proc_tree, x, y, w)
		if ctx.proc_above_was_hidden:
			draw_hidden_process_separator(ctx, y)
			ctx.proc_above_was_hidden = False

	next_y = y + C.proc_h

	for child in proc.child_list:
		child_x, child_y = draw_processes_recursively(ctx, child, proc_tree, next_y)
		if proc.draw and child.draw:
			# XX  draws lines on top of the process name label
			pass # draw_process_connecting_lines(ctx, x, y, child_x, child_y)
		next_y += C.proc_h * proc_tree.num_nodes_drawn([child])  # XX why a second recursion?

	return x, y

def draw_hidden_process_separator(ctx, y):
	ctx.cr.save()
	def draw_again():
		ctx.cr.move_to(ctx.cr.clip_extents()[0], y)
		ctx.cr.line_to(ctx.cr.clip_extents()[2], y)
		ctx.cr.stroke()
	ctx.cr.set_line_width(1.0)
	ctx.cr.set_source_rgb(1.0, 1.0, 1.0)
	draw_again()
	ctx.cr.set_source_rgb(0.3, 0.3, 0.3)
	ctx.cr.set_dash([1, 6])
	draw_again()
	ctx.cr.restore()

def draw_process_activity_colors(ctx, proc, proc_tree, x, y, w):
	draw_fill_rect(ctx.cr, PROC_COLOR_S, (x, y, w, C.proc_h))

	ctx_save__csec_to_xscaled(ctx)
	# draw visual reminder of unknowability of thread end time
	ctx.cr.move_to(proc.samples[-1].time + proc_tree.sample_period, y+C.proc_h/2)
	ctx.cr.line_to(proc.samples[-1].time, y+C.proc_h)
	ctx.cr.line_to(proc.samples[-1].time, y)
	ctx.cr.close_path()
	ctx.cr.fill()

	# cases:
	#    1. proc started before sampling did
	#          XX  should look up time of previous sample, not assume 'proc_tree.sample_period'
	#    2. proc start after sampling
	last_time = max(proc.start_time,
			proc.samples[0].time - proc_tree.sample_period)
	for sample in proc.samples:
		normalized = sample.cpu_sample.user + sample.cpu_sample.sys
		if normalized > 0:
			width = sample.time - last_time
			height = normalized * C.proc_h
			draw_fill_rect(ctx.cr, PROC_COLOR_R, (last_time, y+C.proc_h, width, -height))

			# If thread ran at all, draw a pair of tick marks, in case rect was too short to resolve.
			tick_width = width/3
			tick_height = C.proc_h/3

			ctx.cr.move_to(last_time + width/2, y+C.proc_h-tick_height)
			ctx.cr.rel_line_to(-tick_width/2, tick_height)
			ctx.cr.rel_line_to(tick_width, 0)
			ctx.cr.close_path()
			ctx.cr.fill()

		last_time = sample.time
	ctx.cr.restore()

def usec_to_csec(usec):
	'''would drop precision without the float() cast'''
	return float(usec) / 1000 / 10

def draw_process_events(ctx, proc, proc_tree, x, y):
	ev_list = [(ev, csec_to_xscaled(ctx, usec_to_csec(ev.time_usec)))
		   for ev in proc.events]
	if not ev_list:
		return
	if ctx.SWEEP_CSEC:
		time_origin_relative = ctx.SWEEP_CSEC[0]
	elif ctx.app_options.absolute_uptime_event_times:
		time_origin_relative = 0
	else:
		# align to time of first sample
		time_origin_relative = ctx.time_origin_drawn + proc_tree.sample_period

	# draw ticks, maybe add to dump list
	for (ev, tx) in ev_list:
		if re.search(ctx.highlight_event__func_file_line_RE, ev.func_file_line):
			ctx.cr.set_source_rgba(*HIGHLIGHT_EVENT_COLOR)
			W,H = 2,8
		else:
			ctx.cr.set_source_rgba(*EVENT_COLOR)
			W,H = 1,5
		# don't dump synthetic events
		if ctx.event_dump_list != None and ctx.SWEEP_CSEC and ev.raw_log_seek:
			ev_time_csec = float(ev.time_usec)/1000/10
			if ev_time_csec >= ctx.SWEEP_CSEC[0] and ev_time_csec < ctx.SWEEP_CSEC[1]:
				ctx.event_dump_list.append(ev)
		ctx.cr.move_to(tx-W, y+C.proc_h) # bottom-left
		ctx.cr.rel_line_to(W,-H)       # top
		ctx.cr.rel_line_to(W, H)       # bottom-right
		ctx.cr.close_path()
		ctx.cr.fill()

	# draw numbers
	if not ctx.app_options.print_event_times:
		return
	ctx.cr.set_source_rgba(*EVENT_COLOR)
	spacing = ctx.cr.text_extents("00")[2]
	last_x_touched = 0
	last_label_str = None
	for (ev, tx) in ev_list:
		if tx < last_x_touched + spacing:
			continue
		delta = float(ev.time_usec)/1000/10 - time_origin_relative
		if ctx.SWEEP_CSEC:
			if abs(delta) < C.CSEC:
				label_str = '{0:3d}'.format(int(delta*10))
			else:
				label_str = '{0:.{prec}f}'.format(float(delta)/C.CSEC,
								  prec=min(3, max(1, abs(int(3*C.CSEC/delta)))))
		else:
			# format independent of delta
			label_str = '{0:.{prec}f}'.format(float(delta)/C.CSEC,
							  prec=min(3, max(0, int(ctx.SEC_W/100))))
		if label_str != last_label_str:
			last_x_touched = tx + draw_label_in_box_at_time(
				ctx.cr, PROC_TEXT_COLOR,
				label_str,
				y + C.proc_h - 4, tx)
			last_label_str = label_str

def draw_process_state_colors(ctx, proc, proc_tree, x, y, w):
	last_tx = -1
	for sample in proc.samples :
		tx = csec_to_xscaled(ctx, sample.time)
		state = get_proc_state( sample.state )
		if state == STATE_WAITING or state == STATE_RUNNING:
			color = STATE_COLORS[state]
			ctx.cr.set_source_rgba(*color)
			draw_diamond(ctx.cr, tx, y + C.proc_h/2, 2.5, C.proc_h)

def draw_process_connecting_lines(ctx, px, py, x, y):
	ctx.cr.set_source_rgba(*DEP_COLOR)
	ctx.cr.set_dash([1, 2])   # XX  repeated draws are not phase-synchronized, resulting in a solid line
	if abs(px - x) < 3:
		dep_off_x = 3
		dep_off_y = C.proc_h / 4
		ctx.cr.move_to(x, y + C.proc_h / 2)
		ctx.cr.line_to(px - dep_off_x, y + C.proc_h / 2)
		ctx.cr.line_to(px - dep_off_x, py - dep_off_y)
		ctx.cr.line_to(px, py - dep_off_y)
	else:
		ctx.cr.move_to(x, y + C.proc_h / 2)
		ctx.cr.line_to(px, y + C.proc_h / 2)
		ctx.cr.line_to(px, py)
	ctx.cr.stroke()
	ctx.cr.set_dash([])

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

	ctx.cr.set_line_width(1)

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

		ctx.cr.set_source_rgba(*cs.get_color())
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
				ctx.cr.rectangle (x, below[last_time] - last_cuml, w, last_cuml)
				ctx.cr.fill()
#				ctx.cr.stroke()
				last_time = time
				y = below [time] - cuml

			row[time] = y

		# render the last segment
		x = chart_bounds[0] + round((last_time - proc_tree.start_time) * chart_bounds[2] / proc_tree.duration())
		y = below[last_time] - cuml
		ctx.cr.rectangle (x, y, chart_bounds[2] - x, cuml)
		ctx.cr.fill()
#		ctx.cr.stroke()

		# render legend if it will fit
		if cuml > 8:
			label = cs.cmd
			extnts = ctx.cr.text_extents(label)
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

	draw_box (ctx, chart_bounds)

	# render labels
	for l in labels:
		draw_text(ctx.cr, l[0], TEXT_COLOR, l[1], l[2])

	# Render legends
	font_height = 20
	label_width = 300
	LEGENDS_PER_COL = 15
	LEGENDS_TOTAL = 45
	ctx.cr.set_font_size (TITLE_FONT_SIZE)
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

	draw_text(ctx.cr, label, TEXT_COLOR, chart_bounds[0],
		  chart_bounds[1] + font_height)

	i = 0
	legends.sort(lambda a, b: cmp (b[1], a[1]))
	ctx.cr.set_font_size(TEXT_FONT_SIZE)
	for t in legends:
		cs = t[0]
		time = t[1]
		x = chart_bounds[0] + int (i/LEGENDS_PER_COL) * label_width
		y = chart_bounds[1] + font_height * ((i % LEGENDS_PER_COL) + 2)
		str = "%s - %.0f(ms) (%2.2f%%)" % (cs.cmd, time/1000000, (time/total_time) * 100.0)
		draw_legend_box(ctx.cr, str, cs.color, x, y, C.leg_s)
		i = i + 1
		if i >= LEGENDS_TOTAL:
			break
