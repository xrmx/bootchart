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
import collections
import traceback # debug

from samples import IOStat, EventSample, PID_SCALE, LWP_OFFSET
from . import writer

# Constants: Put the more heavily used, non-derived constants in a named tuple, for immutability.
# XX  The syntax is awkward, but more elegant alternatives have run-time overhead.
#     http://stackoverflow.com/questions/4996815/ways-to-make-a-class-immutable-in-python
DrawConsts = collections.namedtuple('XXtypename',
    #                                        |height of a process, in user-space
    #                                        |                |taskstats-specific
            ['CSEC','bar_h','off_x','off_y','proc_h','leg_s','CUML_HEIGHT','MIN_IMG_W','legend_indent'])
C = DrawConsts( 100,     55,     10,     10,      16,     11,         2000,        800, 5)

# Derived constants
#   XX  create another namedtuple for these
meminfo_bar_h = 2 * C.bar_h

# Process tree background color.
BACK_COLOR = (1.0, 1.0, 1.0, 1.0)

TRANSPARENT = (0.0, 0.0, 0.0, 0.0)

WHITE = (1.0, 1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0, 1.0)
DARK_GREY = (0.1, 0.1, 0.1)
NOTEPAD_YELLOW = (0.95, 0.95, 0.8, 1.0)
NOTEPAD_PINK = (1.0, 0.90, 1.0, 1.0)
PURPLE = (0.6, 0.1, 0.6, 1.0)
RED = (1.0, 0.0, 0.0)
MAGENTA = (0.7, 0.0, 0.7, 1.0)

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
CPU_COLOR = (0.60, 0.60, 0.70, 1.0)
# CPU system-mode load chart color.
CPU_SYS_COLOR = (0.70, 0.65, 0.40, 1.0)
# IO wait chart color.
IO_COLOR = (0.88, 0.74, 0.74, 1.0)

PROCS_RUNNING_COLOR = (0.0, 1.0, 0.0, 1.0)
PROCS_BLOCKED_COLOR = (0.7, 0.0, 0.0, 1.0)

DISK_READ_COLOR = (0.20, 0.71, 0.20, 1.0)
DISK_WRITE_COLOR = MAGENTA

# Mem cached color
MEM_CACHED_COLOR = CPU_COLOR
# Mem used color
MEM_USED_COLOR = IO_COLOR
# Buffers color
MEM_BUFFERS_COLOR = (0.4, 0.4, 0.4, 0.3)
# Swap color
MEM_SWAP_COLOR = (0.20, 0.71, 0.20, 1.0)

# Process CPU load of children -- including those waited for by the parent, but not captured by any collector sample
CPU_CHILD_COLOR = (1.00, 0.70, 0.00, 1.0)
# Process border color.
PROC_BORDER_COLOR = (0.71, 0.71, 0.71, 1.0)
# Waiting process color.
PROC_COLOR_D = PROCS_BLOCKED_COLOR   # (0.76, 0.45, 0.35, 1.0)
# Running process color.
PROC_COLOR_R = CPU_COLOR   # (0.40, 0.50, 0.80, 1.0)  # should look similar to CPU_COLOR
# Sleeping process color.
PROC_COLOR_S = (0.95, 0.93, 0.93, 1.0)
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
DIM_EVENT_COLOR =       (0.2, 0.2, 0.2)
HIGHLIGHT_EVENT_COLOR = (0.4, 0.0, 0.6)

# Signature color.
SIG_COLOR = (0.0, 0.0, 0.0, 0.3125)
# Signature font.
SIG_FONT_SIZE = 14
# Signature text.
SIGNATURE = "http://github.com/mmeeks/bootchart"

# Process dependency line color.
DEP_COLOR = (0.75, 0.6, 0.75, 1.0)
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
	return cr.text_extents(text)[2]

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
	return draw_text(cr, label, TEXT_COLOR, x + w, y)

def draw_legend_box(cr, label, fill_color, x, y, s):
	draw_fill_rect(cr, fill_color, (x, y - s, s, s))
	return s + 5 + draw_text(cr, label, TEXT_COLOR, x + s + 5, y)

def draw_legend_line(cr, label, fill_color, x, y, s):
	draw_fill_rect(cr, fill_color, (x, y - s/2, s + 1, 3))
	cr.fill()
	draw_text(cr, label, TEXT_COLOR, x + s + 5, y)

def draw_label_at_time(cr, color, label, y, label_x):
	draw_text(cr, label, color, label_x, y)
	return cr.text_extents(label)[2] # return width

# y is at process bar boundary above
def draw_label_on_bg(cr, bg_color, color, label, y, label_x):
	TOP_MARGIN=3  # user-space
	label = label
	x_bearing, y_bearing, width, height, x_advance, y_advance = cr.text_extents(label)
	draw_fill_rect(cr, bg_color, (label_x, y+1, x_advance, C.proc_h-2))
	draw_text(cr, label, color, label_x, y-y_bearing+TOP_MARGIN)
	return x_advance

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

		self.ps_event_lists_valid = False

		self.event_dump_list = None
		self.trace = trace

		self.cr = None                # Cairo rendering context
		self.time_origin_drawn = None # time of leftmost plotted data, as integer csecs
		self.SEC_W = None
		self.time_origin_relative = None  # currently used only to locate events

		# intra-rendering state
		self.hide_process_y = None
		self.unhide_process_y = None
		self.proc_above_was_hidden = False

	def _validate_event_state(self, ctx, trace):
		def copy_if_enabled(color_list, re_index):
			return [ec.color_regex[re_index] for ec in color_list if ec.enable]

		self.event_RE = copy_if_enabled( self.app_options.event_color, 0)
		self.event_interval_0_RE = copy_if_enabled( self.app_options.event_interval_color, 0)
		self.event_interval_1_RE = copy_if_enabled( self.app_options.event_interval_color, 1)

		if trace.ps_threads_stats:
			key_fn = lambda ev: ev.tid * PID_SCALE + LWP_OFFSET
		else:
			key_fn = lambda ev: ev.pid * PID_SCALE

		p_map = trace.ps_stats.process_map

		# Copy events selected by currently enabled EventSources to per-process lists
	        for proc in p_map.values():
			proc.events = []
	        for ep in filter(lambda ep: ep.enable, ctx.app_options.event_source.itervalues()):
			for ev in ep.parsed:
				key = key_fn(ev)
				if key in p_map:
					p_map[key].events.append(ev)
				else:
					writer.warn("no samples of /proc/%d/task/%d/stat found -- event lost:\n\t%s" %
						    (ev.pid, ev.tid, ev.raw_log_line))

		# Strip out from per-process lists any events not selected by a regexp.
	        for proc in p_map.values():
			enabled_events = []
			for ev in proc.events:
				# Separate attrs, because they may be drawn differently
				ev.event_match_any = None
				ev.event_match_0 = None
				ev.event_match_1 = None
                                def _set_attr_on_match(RE_list, event_match_attr):
                                        # Only LAST matching regexp contributes to the label string --
                                        # this allows user to append overriding regexes to the command line.
                                        m = None
                                        for ev_re in RE_list:
                                                m = re.search(ev_re, ev.raw_log_line)
                                                if m:
                                                        setattr(ev, event_match_attr, m)
                                        return getattr(ev, event_match_attr) is not None
                                _set_attr_on_match(ctx.event_RE + ctx.event_interval_0_RE + ctx.event_interval_1_RE,
                                                  "event_match_any")
                                _set_attr_on_match(ctx.event_interval_0_RE, "event_match_0")
                                _set_attr_on_match(ctx.event_interval_1_RE, "event_match_1")
				enabled_events.append(ev)
			enabled_events.sort(key = lambda ev: ev.time_usec)
			proc.events = enabled_events
			proc.draw |= len(proc.events) > 0
		self.ps_event_lists_valid = True

	def per_render_init(self, cr, ctx, trace, time_origin_drawn, SEC_W, sweep_csec):
		self.cr = cr
		self.time_origin_drawn = time_origin_drawn
		self.SEC_W = SEC_W
		self.n_WIDTH = cr.text_extents("n")[2]
		self.M_HEIGHT = cr.text_extents("M")[3]

	        # merge in enabled event sources
		if not self.ps_event_lists_valid:
			self._validate_event_state(ctx, trace)

		self.SWEEP_CSEC = sweep_csec
		if self.SWEEP_CSEC:
			self.SWEEP_CSEC.sort()
			self.time_origin_relative = self.SWEEP_CSEC[0]
		elif self.app_options.absolute_uptime_event_times:
			self.time_origin_relative = 0
		else:
			# align to time of first sample
			self.time_origin_relative = self.time_origin_drawn + self.trace.proc_tree.sample_period

	def proc_tree (self, trace):
		return trace.kernel_tree if self.kernel_only else trace.proc_tree

	def draw_process_label_in_box(self, color, bg_color, label,
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
		draw_fill_rect(self.cr, bg_color, (label_x, y-1, label_w, -(C.proc_h-2)))
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

def draw_box_1(ctx, rect):
	""" draws an outline one user-space unit in width around rect.
	For best appearance with the default transform (or zoom to an odd multiple),
	the corners of rect should be offset by USER_HALF (0.5).
	This is a consequence of Cairo's line-drawing model."""
	# XX  But zooming currently is in steps of sqrt(2) -- what solution would give
	#     both pixel-aligned lines, and reasonble zoom steps?
	#           ... 1/8, 1/6, 1/4, 1/3, 1/2, 1/sqrt(2), 1, sqrt(2), 2, 3, 4, 5, 6, 8, ...
	# XX  Drawing within the chart should be similarly aligned.
	ctx.cr.save()
	ctx.cr.set_line_width(1.0)
	draw_rect(ctx.cr, BORDER_COLOR, tuple(rect))
	ctx.cr.restore()

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
def plot_segment(cr, point, x, y, segment_tick_height):
	cr.move_to(cr.get_current_point()[0], y)       # upward or downward
	if point[1] <= 0:           # zero-Y samples draw nothing
		cr.move_to(x, y)
		return
	#cr.set_line_width(1.0)
	cr.line_to(x, y-segment_tick_height/2)
	cr.rel_line_to(0, segment_tick_height)
	cr.fill()
	cr.move_to(x, y)

SEGMENT_TICK_HEIGHT = 2
def plot_segment_thin(cr, point, x, y):
	plot_segment(cr, point, x, y, SEGMENT_TICK_HEIGHT)

def plot_segment_fat(cr, point, x, y):
	plot_segment(cr, point, x, y, 1.5*SEGMENT_TICK_HEIGHT)

def _plot_scatter_positive(cr, point, x, y, w, h):
	if point[1] <= 0:
		return
	draw_diamond(cr, x, y, w, h)

def plot_scatter_positive_big(cr, point, x, y):
	return _plot_scatter_positive(cr, point, x, y, 5.5, 5.5)

def plot_scatter_positive_small(cr, point, x, y):
	return _plot_scatter_positive(cr, point, x, y, 3.6, 3.6)

# All charts assumed to be full-width
# XX horizontal coords in chart_bounds are now on-pixel-center
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
	return max_y

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
	x_onscreen = max(0, ctx.cr.device_to_user(0, 0)[0])

	max_procs_blocked = \
		max([sample.procs_blocked for sample in trace.cpu_stats])
	max_procs_running = \
		max([sample.procs_running for sample in trace.cpu_stats])

	if ctx.app_options.show_legends:
		# render bar legend
		ctx.cr.set_font_size(LEGEND_FONT_SIZE)
		curr_y += 20
		curr_x = C.legend_indent + x_onscreen
		curr_x += 20 + draw_legend_box(ctx.cr, "CPU (user)", CPU_COLOR, curr_x, curr_y, C.leg_s)
		curr_x += 20 + draw_legend_box(ctx.cr, "CPU (sys)", CPU_SYS_COLOR, curr_x, curr_y, C.leg_s)
		curr_x += 20 + draw_legend_box(ctx.cr, "I/O (wait)", IO_COLOR, curr_x, curr_y, C.leg_s)
		curr_x += draw_legend_diamond(ctx.cr, str(max_procs_running) + " Runnable threads",
				PROCS_RUNNING_COLOR, curr_x +10, curr_y, C.leg_s, C.leg_s)
		curr_x += draw_legend_diamond(ctx.cr, str(max_procs_blocked) + " Blocked threads -- Uninterruptible Syscall",
				PROCS_BLOCKED_COLOR, curr_x +70, curr_y, C.leg_s, C.leg_s)

	chart_rect = (0, curr_y+10+USER_HALF, w, C.bar_h)
	draw_box_1 (ctx, chart_rect)
	draw_annotations (ctx, proc_tree, trace.times, chart_rect)
	# render I/O wait -- a backwards delta
	draw_chart (ctx, IO_COLOR, True, chart_rect, \
		    [(sample.time, sample.user + sample.sys + sample.io) for sample in trace.cpu_stats], \
		    proc_tree,
		    [0, 1],
		    plot_square)
	# render CPU load -- a backwards delta
	draw_chart (ctx, CPU_COLOR, True, chart_rect, \
		    [(sample.time, sample.user + sample.sys) for sample in trace.cpu_stats], \
		    proc_tree,
		    [0, 1],
		    plot_square)
	# superimpose "sys time", the fraction of CPU load spent in kernel -- a backwards delta
	draw_chart (ctx, CPU_SYS_COLOR, True, chart_rect, \
		    [(sample.time, sample.sys) for sample in trace.cpu_stats], \
		    proc_tree,
		    [0, 1],
		    plot_square)

	# instantaneous sample
	draw_chart (ctx, PROCS_BLOCKED_COLOR, False, chart_rect,
		    [(sample.time, sample.procs_blocked) for sample in trace.cpu_stats], \
		    proc_tree, [0, max(max_procs_blocked, max_procs_running)], plot_scatter_positive_big)

	# instantaneous sample
	draw_chart (ctx, PROCS_RUNNING_COLOR, False, chart_rect,
		    [(sample.time, sample.procs_running) for sample in trace.cpu_stats], \
		    proc_tree, [0, max(max_procs_blocked, max_procs_running)], plot_scatter_positive_small)

	curr_y += 8 + C.bar_h

	# XXX  Assume single device for now.
	# XX   Generate an IOStat containing max'es of all stats, instead?
	max_whole_device_IOStat = IOStat._make(
		getattr( max( trace.disk_stats[0].part_deltas,
			      key = lambda part_delta: getattr(part_delta.s.iostat, f)).s.iostat,
			 f)
		for f in IOStat._fields)
	max_whole_device_util = \
		max( trace.disk_stats[0].part_deltas,
		     key = lambda part_delta: part_delta.util).util

	if ctx.app_options.show_ops_not_bytes:
		read_field = 'nreads'
		write_field = 'nwrites'
	else:
		read_field = 'nsectors_read'
		write_field = 'nsectors_write'

	max_whole_device_read_or_write = max(getattr(max_whole_device_IOStat, write_field),
					     getattr(max_whole_device_IOStat, read_field))

	if ctx.app_options.show_legends:
		curr_y += 34
		curr_x = C.legend_indent+x_onscreen
		# render second chart
		draw_legend_box(ctx.cr,
				"Disk utilization -- fraction of sample interval I/O queue was not empty",
				IO_COLOR, curr_x, curr_y, C.leg_s)
		curr_x += 457

		def draw_RW_legend(x, field, color, plot):
			label = str(getattr(max_whole_device_IOStat, field)) + " " + field
			cr = ctx.cr
			cr.set_source_rgba(*color)
			cr.move_to(x, -1)
			PLOT_WIDTH = 30
			plot(cr, [0,1], x+PLOT_WIDTH, curr_y-4)
			x += PLOT_WIDTH+5
			x += draw_text(cr, label, TEXT_COLOR, x, curr_y)
			return x

		curr_x = 10 + draw_RW_legend(curr_x,
				read_field, DISK_READ_COLOR, plot_segment_thin)
		curr_x = draw_RW_legend(curr_x,
				write_field, DISK_WRITE_COLOR, plot_segment_fat)
		if ctx.app_options.show_ops_not_bytes:
			curr_x = draw_RW_legend(curr_x,
						"nio_in_progress", BLACK, plot_scatter_positive_big)

        # render I/O utilization
	#  No correction for non-constant sample.time -- but see sample-coalescing code in parsing.py.
	for partition in trace.disk_stats:
		if partition.hide:
			continue
		draw_text(ctx.cr, partition.label, TEXT_COLOR, C.legend_indent+x_onscreen, curr_y+18)

		# utilization -- inherently normalized [0,1]
		chart_rect = (0, curr_y+18+5+USER_HALF, w, C.bar_h)
		draw_box_1 (ctx, chart_rect)
		draw_annotations (ctx, proc_tree, trace.times, chart_rect)
		# a backwards delta
		draw_chart (ctx, IO_COLOR, True, chart_rect,
				    [(sample.s.time, sample.util) for sample in partition.part_deltas],
				    proc_tree, [0, max_whole_device_util], plot_square)

		# write throughput -- a backwards delta
		draw_chart (ctx, DISK_WRITE_COLOR, False, chart_rect,
			[(sample.s.time, getattr(sample.s.iostat, write_field)) for sample in partition.part_deltas],
			proc_tree, [0, max_whole_device_read_or_write], plot_segment_fat)

		# overlay read throughput -- any overlapping read will be protrude around the edges
		draw_chart (ctx, DISK_READ_COLOR, False, chart_rect,
			[(sample.s.time, getattr(sample.s.iostat, read_field)) for sample in partition.part_deltas],
			proc_tree, [0, max_whole_device_read_or_write], plot_segment_thin)

		# overlay instantaneous count of number of I/O operations in progress, only if comparable to
		# the read/write stats currently shown (ops).
		if ctx.app_options.show_ops_not_bytes:
			draw_chart (ctx, BLACK, False, chart_rect,
				    [(sample.s.time, sample.nio_in_progress) for sample in partition.part_deltas],
				    proc_tree,
				    [0, max(max_whole_device_read_or_write,
					    max_whole_device_IOStat.nio_in_progress)],
				     plot_scatter_positive_small)

		curr_y += 18+C.bar_h

	# render mem usage
	chart_rect = (0, curr_y+30+USER_HALF, w, meminfo_bar_h)
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
		draw_box_1 (ctx, chart_rect)
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
# Render the chart.  Main entry point of this module.
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
	ctx.per_render_init(cr, ctx, trace, _time_origin_drawn(ctx, trace), _sec_w(xscale), sweep_csec)
	(w, h) = extents(ctx, xscale, trace)

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

	if ctx.app_options.show_legends and not ctx.kernel_only:
		curr_y = draw_process_bar_chart_legends(ctx, curr_y)

	# draw process boxes
	proc_height = h
	if proc_tree.taskstats and ctx.cumulative:
		proc_height -= C.CUML_HEIGHT

	curr_y += ctx.M_HEIGHT

	# curr_y points to the *top* of the first per-process line
	if hide_process_y and hide_process_y[0] > (curr_y - C.proc_h/4):
		hide_mod_proc_h = (hide_process_y[0] - curr_y) % C.proc_h
		# if first button-down (hide_process_y[0]) falls in middle half of any process bar, then set up for hiding
		if hide_mod_proc_h >= C.proc_h/4 and hide_mod_proc_h < C.proc_h*3/4:
				hide_process_y.sort()
				ctx.hide_process_y = hide_process_y
				ctx.unhide_process_y = None
		else: # unhide
			ctx.hide_process_y = None
			ctx.unhide_process_y = hide_process_y[0]

	curr_y = draw_process_bar_chart(ctx, proc_tree, trace.times,
					curr_y, w, proc_height)

	if proc_tree.taskstats and ctx.cumulative:
		# draw a cumulative CPU-time-per-process graph
		cuml_rect = (0, proc_height + C.off_y, w, C.CUML_HEIGHT/2 - C.off_y * 2)
		draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_CPU)

		# draw a cumulative I/O-time-per-process graph
		cuml_rect = (0, proc_height + C.off_y * 100, w, C.CUML_HEIGHT/2 - C.off_y * 2)
		draw_cuml_graph(ctx, proc_tree, cuml_rect, duration, STAT_TYPE_IO)

	if ctx.SWEEP_CSEC:
		draw_sweep(ctx)

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
			if event0.raw_log_seek:
				event0.raw_log_file.seek(event0.raw_log_seek)
				eventN = ctx.event_dump_list[-1]
				# for line in event0.raw_log_file.readline():
				while event0.raw_log_file.tell() <= eventN.raw_log_seek:
					print event0.raw_log_file.readline().rstrip()
	else:   # dump only digestible events
		ctx.event_dump_list.sort(key = lambda ev: ev.time_usec)
		for ev in ctx.event_dump_list:
			print ev.dump_format()

	ctx.event_dump_list = None

def draw_sweep(ctx):
	def draw_shading(cr, rect):
		# alpha value of the rgba strikes a compromise between appearance on screen, and in printed screenshot
		cr.set_source_rgba(0.0, 0.0, 0.0, 0.08)
		cr.set_line_width(0.0)
		cr.rectangle(rect)
		cr.fill()
	def draw_vertical(ctx, time, x):
		cr = ctx.cr
		cr.set_dash([1, 3])
		cr.set_source_rgba(0.0, 0.0, 0.0, 1.0)
		cr.set_line_width(1.0)
		cr.move_to(x, 0)
		cr.line_to(x, height)
		cr.stroke()

	height = int(ctx.cr.device_to_user(0,2000)[1])
	x_itime = [None, None]
	for i_time, time in enumerate(ctx.SWEEP_CSEC):
		time = ctx.SWEEP_CSEC[i_time]
		x = csec_to_xscaled(ctx, time)
		draw_shading(ctx.cr, (int(x),0,int(ctx.cr.clip_extents()[i_time*2]-x),height))
		draw_vertical(ctx, time, x)
		x_itime[i_time] = x

	top = ctx.cr.device_to_user(0, 0)[1]
	origin = 0 if ctx.app_options.absolute_uptime_event_times else \
		 ctx.time_origin_drawn + ctx.trace.proc_tree.sample_period
	draw_label_on_bg(ctx.cr, NOTEPAD_YELLOW, BLACK,
			 "{0:.6f}".format((ctx.SWEEP_CSEC[0] - origin)/C.CSEC),
			 top,
			 x_itime[0] + ctx.n_WIDTH/2)
	if i_time == 0:
		return
	draw_label_on_bg(ctx.cr, NOTEPAD_YELLOW, BLACK,
			 "+{0:.6f}".format((ctx.SWEEP_CSEC[1] - ctx.SWEEP_CSEC[0])/C.CSEC),
			 top + ctx.M_HEIGHT*2,
			 x_itime[1] + ctx.n_WIDTH/2)

def draw_process_bar_chart_legends(ctx, curr_y):
	curr_y += 30
	curr_x = 10 + C.legend_indent + max(0, ctx.cr.device_to_user(0, 0)[0])
	curr_x += 30 + draw_legend_diamond (ctx.cr, "Runnable",
				       PROCS_RUNNING_COLOR, curr_x, curr_y, C.leg_s*3/4, C.proc_h)
	curr_x += 30 + draw_legend_diamond (ctx.cr, "Uninterruptible Syscall",
				       PROC_COLOR_D, curr_x, curr_y, C.leg_s*3/4, C.proc_h)
	curr_x += 20 + draw_legend_box (ctx.cr, "Running (user)",
				   PROC_COLOR_R, curr_x, curr_y, C.leg_s)
	curr_x += 20 + draw_legend_box (ctx.cr, "Running (sys)",
				   CPU_SYS_COLOR, curr_x, curr_y, C.leg_s)
	curr_x += 20 + draw_legend_box (ctx.cr, "I/O wait",
				   IO_COLOR, curr_x, curr_y, C.leg_s)
        curr_x += 20 + draw_legend_box (ctx.cr, "Child CPU time lost, charged to parent",
				   CPU_CHILD_COLOR, curr_x, curr_y, C.leg_s)
	curr_x += 20 + draw_legend_box (ctx.cr, "Sleeping",
				   PROC_COLOR_S, curr_x, curr_y, C.leg_s)
	curr_x += 20 + draw_legend_box (ctx.cr, "Zombie",
				   PROC_COLOR_Z, curr_x, curr_y, C.leg_s)
	curr_y -= 15
	return curr_y

def draw_process_bar_chart(ctx, proc_tree, times, curr_y, w, h):
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
		if not root.lwp():
			curr_y = draw_processes_recursively(ctx, root, proc_tree, curr_y)[1]
	if ctx.proc_above_was_hidden:
		draw_hidden_process_separator(ctx, curr_y)
		ctx.proc_above_was_hidden = False
	return curr_y

def draw_header (ctx, headers, duration):
    toshow = [
      ('system.uname', 'uname', lambda s: s),
      ('system.release', 'release', lambda s: s),
      ('system.cpu', 'CPU', lambda s: re.sub('model name\s*:\s*', '', s, 1)),
      ('system.kernel.options', 'kernel options', lambda s: s),
    ]
    toshow = []

    cr = ctx.cr
    header_y = cr.font_extents()[2] + 10
    cr.set_font_size(TITLE_FONT_SIZE)
    x_onscreen = C.legend_indent + max(0, ctx.cr.device_to_user(0, 0)[0])
    draw_text(cr, headers['title'], TEXT_COLOR, x_onscreen, header_y)
    cr.set_font_size(TEXT_FONT_SIZE)

    for (headerkey, headertitle, mangle) in toshow:
        header_y += cr.font_extents()[2]
        if headerkey in headers:
            value = headers.get(headerkey)
        else:
            value = ""
        txt = headertitle + ': ' + mangle(value)
        draw_text(cr, txt, TEXT_COLOR, x_onscreen, header_y)

#     dur = duration / 100.0
#     txt = 'time : %02d:%05.2f' % (math.floor(dur/60), dur - 60 * math.floor(dur/60))
#     if headers.get('system.maxpid') is not None:
#         txt = txt + '      max pid: %s' % (headers.get('system.maxpid'))
#
#    header_y += cr.font_extents()[2]
#    draw_text (cr, txt, TEXT_COLOR, 0, header_y)

    return header_y

# Cairo draws lines "on-center", so to draw a one-pixel width horizontal line
# using the (default) 1:1 transform from user-space to device-space,
# the Y coordinate must be offset by 1/2 user-coord.
SEPARATOR_THICKNESS = 1.0
SEP_HALF = SEPARATOR_THICKNESS / 2
USER_HALF = 0.5
BAR_HEIGHT = C.proc_h - SEPARATOR_THICKNESS

def draw_visible_process_separator(ctx, proc, x, y, w):
	ctx.cr.save()
	ctx.cr.set_source_rgba(*PROC_BORDER_COLOR)
	ctx.cr.set_line_width(SEPARATOR_THICKNESS)
	ctx.cr.move_to(x+w, y)
	ctx.cr.rel_line_to(-w, 0)
	if proc.start_time < ctx.time_origin_drawn:
		ctx.cr.stroke()
		ctx.cr.move_to(x, y+C.proc_h)
	else:
		# XX  No attempt to align the vertical line with the device pixel grid
		ctx.cr.rel_line_to(0, C.proc_h)
	ctx.cr.rel_line_to(w, 0)
	ctx.cr.stroke()
	ctx.cr.restore()

def draw_hidden_process_separator(ctx, y):
	DARK_GREY = 1.0, 1.0, 1.0
	GREY = 0.3, 0.3, 0.3
	ctx.cr.save()
	ctx.cr.set_source_rgb(0.0, 1.0, 0.0)
	ctx.cr.set_line_width(SEPARATOR_THICKNESS)
	def draw_again():
		ctx.cr.move_to(ctx.cr.clip_extents()[0], y)
		ctx.cr.line_to(ctx.cr.clip_extents()[2], y)
		ctx.cr.stroke()
	ctx.cr.set_source_rgb(*DARK_GREY)
	draw_again()
	ctx.cr.set_source_rgb(*GREY)
	ctx.cr.set_dash([1, 4])
	draw_again()
	ctx.cr.restore()

def draw_process(ctx, proc, proc_tree, x, y, w):
	draw_process_activity_colors(ctx, proc, proc_tree, x, y, w)

	# Do not draw right-hand vertical border -- process exit never exactly known
	draw_visible_process_separator(ctx, proc, x, y, w)

	if proc.lwp() or not ctx.trace.ps_threads_stats:
		draw_process_state_colors(ctx, proc, proc_tree, x, y, w)

	# Event ticks step on the rectangle painted by draw_process_state_colors(),
	# e.g. for non-interruptible wait.
	# User can work around this by toggling off the event ticks.
	n_highlighted_events = 0 if ctx.app_options.hide_events else \
			       draw_process_events(ctx, proc, proc_tree, x, y)

	if proc_tree.taskstats and ctx.app_options.show_all:
		cmdString = ''
	else:
		cmdString = proc.cmd
	if (ctx.app_options.show_pid or ctx.app_options.show_all) and proc.pid is not 0:
		prefix = " ["
		if ctx.app_options.show_all:
			prefix += str(proc.ppid / 1000) + ":"
		prefix += str(proc.pid / 1000)
		if proc.lwp():
			prefix += ":" + str(proc.tid / 1000)
		prefix += "]"
		cmdString = prefix + cmdString
	if ctx.app_options.show_all and proc.args:
		cmdString += " '" + "' '".join(proc.args) + "'"

	ctx.draw_process_label_in_box( PROC_TEXT_COLOR,
				       NOTEPAD_YELLOW if proc.lwp() else NOTEPAD_PINK,
				       cmdString,
				       csec_to_xscaled(ctx, max(proc.start_time,ctx.time_origin_drawn)),
				       y,
				       w,
				       ctx.cr.device_to_user(0, 0)[0],
				       ctx.cr.clip_extents()[2])
	return n_highlighted_events

def draw_processes_recursively(ctx, proc, proc_tree, y):
	xmin = ctx.cr.device_to_user(0, 0)[0]   # work around numeric overflow at high xscale factors
	xmin = max(xmin, 0)

	def draw_process_and_separator(ctx, proc, proc_tree, y):
		x = max(xmin, csec_to_xscaled(ctx, proc.start_time))
		w = max(xmin, csec_to_xscaled(ctx, proc.start_time + proc.duration)) - x
		if ctx.hide_process_y and y+C.proc_h > ctx.hide_process_y[0] and proc.draw:
			proc.draw = False
			ctx.hide_process_y[1] -= C.proc_h
			if y > (ctx.hide_process_y[1]) / C.proc_h * C.proc_h:
				ctx.hide_process_y = None

		elif ctx.unhide_process_y and y+C.proc_h*3/4 > ctx.unhide_process_y:
			if proc.draw:    # found end of run of hidden processes
				ctx.unhide_process_y = None
			else:
				proc.draw = True
				ctx.unhide_process_y += C.proc_h

		if not proc.draw:
			ctx.proc_above_was_hidden = True
			return x, y
		else:
			n_highlighted_events = draw_process(ctx, proc, proc_tree, x, y+USER_HALF, w)
			if ctx.proc_above_was_hidden:
				draw_hidden_process_separator(ctx, y+USER_HALF)
				ctx.proc_above_was_hidden = False
			return x, y + C.proc_h*(1 if n_highlighted_events <= 0 else 2)

	x, child_y = draw_process_and_separator(ctx, proc, proc_tree, y)

	if proc.lwp_list is not None:
		for lwp in proc.lwp_list:
			x, child_y = draw_process_and_separator(ctx, lwp, proc_tree, child_y)

	elder_sibling_y = None
	for child in proc.child_list:
		# Processes draw their "own" LWPs, contrary to formal parentage relationship
		if child.lwp_list is None:
			continue

		child_x, next_y = draw_processes_recursively(ctx, child, proc_tree, child_y)
		if proc.draw and child.draw:
			# draw upward from child to elder sibling or parent (proc)
			# XX  draws lines on top of the process name label
			#draw_process_connecting_lines(ctx, x, y, child_x, child_y, elder_sibling_y)
			elder_sibling_y = child_y
		child_y = next_y
	return x, child_y

def draw_process_activity_colors(ctx, proc, proc_tree, x, y, w):
	draw_fill_rect(ctx.cr, PROC_COLOR_S, (x, y, w, C.proc_h))

	ctx_save__csec_to_xscaled(ctx)
	ctx.cr.set_line_width(0.0)
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
            cpu_self = sample.cpu_sample.user + sample.cpu_sample.sys
	    cpu_exited_child = 0   # XXXX   sample.exited_child_user + sample.exited_child_sys
	    width = sample.time - last_time

	    if cpu_exited_child > 0:
		height = (cpu_exited_child + cpu_self) * BAR_HEIGHT
		draw_fill_rect(ctx.cr, CPU_CHILD_COLOR, (last_time, y+C.proc_h-SEP_HALF, width, -height))

	    if cpu_exited_child != 0:
		    print "cpu_exited_child == " + str(cpu_exited_child)

	    # XX  For whole processes, the cpu_sample.io stat is the sum of waits for all threads.

	    # Inspection of kernel code shows that tick counters are rounded to nearest,
	    # so overflow is to be expected.
	    OVERFLOW_LIMIT=1.0
	    # XX  What's the upper bound on rounding-induced overflow?
	    if sample.cpu_sample.io + cpu_self > 0:
	        height = min(OVERFLOW_LIMIT, (sample.cpu_sample.io + cpu_self)) * BAR_HEIGHT
	        draw_fill_rect(ctx.cr, IO_COLOR, (last_time, y+C.proc_h-SEP_HALF, width, -height))

		for (cpu_field, color) in [(sample.cpu_sample.user + sample.cpu_sample.sys, PROC_COLOR_R),
					   (sample.cpu_sample.sys, CPU_SYS_COLOR)]:
	            # If this test fails -- no time ticks -- then skip changing of color.
	            if cpu_field > 0:
			    height = min(OVERFLOW_LIMIT, cpu_field) * BAR_HEIGHT
			    draw_fill_rect(ctx.cr, color, (last_time, y+C.proc_h-SEP_HALF, width, -height))
			    if cpu_field < cpu_self:
				    # draw a separator between the bar segments, to aid the eye in
				    # resolving the boundary
				    ctx.cr.save()
				    ctx.cr.move_to(last_time, y+C.proc_h-SEP_HALF-height)
				    ctx.cr.rel_line_to(width,0)
				    ctx.cr.set_source_rgba(*PROC_COLOR_S)
				    ctx.cr.set_line_width(DEP_STROKE/2)
				    ctx.cr.stroke()
				    ctx.cr.restore()

	        # If thread ran at all, draw a "speed bump", in the last used color, to help the user
		# with rects that are too short to resolve.
	        tick_height = C.proc_h/5
	        ctx.cr.arc((last_time + sample.time)/2, y+C.proc_h-SEP_HALF, tick_height, math.pi, 0.0)
	        ctx.cr.close_path()
	        ctx.cr.fill()

	    if cpu_self > 1.0:
		writer.info("process CPU+I/O time overflow: time {0:5d}, start_time {1:5d}, tid {2:5d}, width {3:2d}, cpu_self {4: >5.2f}".format(
			sample.time, proc.start_time, proc.tid/1000, width, cpu_self))
		OVERFLOW_BAR_HEIGHT=2
		draw_fill_rect(ctx.cr, PURPLE, (last_time, y+SEP_HALF, width, OVERFLOW_BAR_HEIGHT))
		cpu_self = 1.0 - float(OVERFLOW_BAR_HEIGHT)/C.proc_h

	    last_time = sample.time
	ctx.cr.restore()

def usec_to_csec(usec):
	'''would drop precision without the float() cast'''
	return float(usec) / 1000 / 10

def csec_to_usec(csec):
	return csec * 1000 * 10

def draw_event_label(ctx, label, tx, y):
	return draw_label_at_time(ctx.cr, HIGHLIGHT_EVENT_COLOR, label, y, tx)

def format_label_time(ctx, delta):
	if ctx.SWEEP_CSEC:
		if abs(delta) < C.CSEC:
			# less than a second, so format as whole milliseconds
			return '{0:d}'.format(int(delta*10))
		else:
			# format as seconds, plus a variable number of digits after the decimal point
			return '{0:.{prec}f}'.format(float(delta)/C.CSEC,
						     prec=min(3, max(1, abs(int(3*C.CSEC/delta)))))
	else:
		# formatting is independent of delta value
		return '{0:.{prec}f}'.format(float(delta)/C.CSEC,
					     prec=min(3, max(0, int(ctx.SEC_W/100))))

def print_event_times(ctx, y, ev_list):
	last_x_touched = 0
	last_label_str = None
	for (ev, tx) in ev_list:
		if not ctx.app_options.synthesize_sample_start_events and ev.raw_log_line == "pseudo-raw_log_line":
			continue
		m_highlight = ev.event_match_any
		delta = usec_to_csec(ev.time_usec) - ctx.time_origin_relative

		label_str = format_label_time(ctx, delta)
		white_space = 8
		if tx < last_x_touched + white_space:
			continue

		if m_highlight or label_str != last_label_str:
			if m_highlight:
				last_x_touched = tx + draw_label_on_bg(
					ctx.cr,
					WHITE,
					HIGHLIGHT_EVENT_COLOR, label_str, y, tx)
			else:
				last_x_touched = tx + draw_label_on_bg(
					ctx.cr,
					TRANSPARENT,
					DIM_EVENT_COLOR, label_str, y, tx)
			last_label_str = label_str

def draw_process_events(ctx, proc, proc_tree, x, y):
	ctx.cr.save()
	ctx.cr.set_line_width(0)

	n_highlighted_events = 0
	last_tx_plus_width_drawn = 0
	ev_list = [(ev, csec_to_xscaled(ctx, usec_to_csec(ev.time_usec)))
		   for ev in proc.events]

	# draw numbers
	if ctx.app_options.print_event_times:
		print_event_times(ctx, y, ev_list)

	# draw ticks, maybe add to dump list
	for (ev, tx) in ev_list:
		if not ctx.app_options.synthesize_sample_start_events and ev.raw_log_line == "pseudo-raw_log_line":
			continue
		last_m = ev.event_match_any
		if last_m:
			ctx.cr.set_source_rgb(*HIGHLIGHT_EVENT_COLOR)
			W = 2
			if last_m.lastindex:
				groups_concat = ""
				for g in last_m.groups():
					groups_concat += str(g)
			else:
				groups_concat = last_m.group(0)
			if last_tx_plus_width_drawn < tx:
				# draw bottom half of tick mark
				tick_depth = 10
				ctx.cr.move_to(tx, y +C.proc_h +tick_depth) # bottom

				ctx.cr.rel_line_to(-W, -tick_depth -0.5)      # top-left
				ctx.cr.rel_line_to(2*W, 0)        # top-right
				ctx.cr.close_path()
				ctx.cr.fill()

				clear = 1.0                        # clearance between down-tick and string
				last_tx_plus_width_drawn = \
						tx + clear + \
						draw_event_label(ctx,
								 groups_concat,
								 tx + clear, y+2*C.proc_h-4)
			n_highlighted_events += 1
		else:
			ctx.cr.set_source_rgb(*DIM_EVENT_COLOR)
			W = 1

		# If an interval bar should start at tx, record the time.
		last_m = ev.event_match_0
		if last_m:
			proc.event_interval_0_tx = tx

		# Draw interval bar that terminates at tx, if any.
		if proc.event_interval_0_tx != None:
			last_m = ev.event_match_1
			if last_m:
				ctx.cr.rectangle(proc.event_interval_0_tx, y+C.proc_h+0.5,
						 tx-proc.event_interval_0_tx, 1.5)
				ctx.cr.fill()
				proc.event_interval_0_tx = None

		if ctx.event_dump_list != None and ctx.SWEEP_CSEC \
			    and ev.raw_log_file:        # don't dump synthetic events
			ev_time_csec = usec_to_csec(ev.time_usec)
			if ev_time_csec >= ctx.SWEEP_CSEC[0] and ev_time_csec < ctx.SWEEP_CSEC[1]:
				ctx.event_dump_list.append(ev)

		# draw top half of tick mark
		ctx.cr.move_to(tx, y+C.proc_h-6.5) # top

		ctx.cr.rel_line_to(-W,6)         # bottom-left
		ctx.cr.rel_line_to(2*W,0)        # bottom-right
		ctx.cr.close_path()
		ctx.cr.fill()

	ctx.cr.restore()
	return n_highlighted_events

def draw_process_state_colors(ctx, proc, proc_tree, x, y, w):
	last_tx = -1
	for sample in proc.samples :
		tx = csec_to_xscaled(ctx, sample.time)
		state = get_proc_state( sample.state )
		if state == STATE_WAITING or state == STATE_RUNNING:
			color = STATE_COLORS[state]
			ctx.cr.set_source_rgba(*color)
			draw_diamond(ctx.cr, tx, y + C.proc_h/2, 2.5, C.proc_h)

def draw_process_connecting_lines(ctx, px, py, x, y, elder_sibling_y):
	ON = 1
	OFF = 2
	DASH_LENGTH = ON + OFF

	ctx.cr.save()
	ctx.cr.set_source_rgba(*DEP_COLOR)
	ctx.cr.set_dash([ON, OFF])   # repeated draws are not phase-synchronized, resulting in a solid line
	ctx.cr.set_line_width(DEP_STROKE)

	ctx.cr.move_to(x, y + C.proc_h / 2)                          # child's center
	# exdent the connecting lines; otherwise the horizontal would be too short to see
	dep_off_x = 3
	dep_off_y = 0 # C.proc_h / 4
	ctx.cr.line_to(px - dep_off_x, y + C.proc_h / 2)             # leftward
	if elder_sibling_y is not None:
		ctx.cr.line_to(px - dep_off_x, elder_sibling_y + C.proc_h/2) # upward
	else:
		ctx.cr.line_to(px - dep_off_x, py + C.proc_h/2)      # upward
		ctx.cr.rel_line_to(dep_off_x, 0)                     # rightward
	ctx.cr.stroke()
	ctx.cr.restore()

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

	draw_box_1 (ctx, chart_bounds)

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
