import math
import optparse
import os
import re
import sys
import struct

# Process tree background color.
BACK_COLOR = (1.0, 1.0, 1.0, 1.0)
# Process tree border color.
BORDER_COLOR = (0.63, 0.63, 0.63, 1.0)
# Second tick line color.
TICK_COLOR = (0.92, 0.92, 0.92, 1.0)
# 5-second tick line color.
TICK_COLOR_BOLD = (0.86, 0.86, 0.86, 1.0)
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
	
# Process border color.
PROC_BORDER_COLOR = (0.71, 0.71, 0.71, 1.0)
# Waiting process color.
PROC_COLOR_D = (0.76, 0.48, 0.48, 0.125)
# Running process color.
PROC_COLOR_R = CPU_COLOR
# Sleeping process color.
PROC_COLOR_S = (0.94, 0.94, 0.94, 1.0)
# Stopped process color.
PROC_COLOR_T = (0.94, 0.50, 0.50, 1.0)
# Zombie process color.
PROC_COLOR_Z = (0.71, 0.71, 0.71, 1.0)

# Process label color.
PROC_TEXT_COLOR = (0.19, 0.19, 0.19, 1.0)
# Process label font.
PROC_TEXT_FONT_SIZE = 12

# Signature color.
SIG_COLOR = (0.0, 0.0, 0.0, 0.3125)
# Signature font.
SIG_FONT_SIZE = 14
# Signature text.
SIGNATURE = "www.bootchart.org"
SIGNATURE = ""
	
# Disk chart line stoke.
DISK_STROKE = 1.5
	
# Process dependency line color.
DEP_COLOR = (0.75, 0.75, 0.75, 1.0)
# Process dependency line stroke.
DEP_STROKE = 1.0

# Minimum image width.
MIN_IMG_W = 800
# Maximum image dimenstion (to avoid OOM exceptions).
MAX_IMG_DIM = 4096

# Process description date format.
DESC_TIME_FORMAT = "mm:ss.SSS"

# Process states
STATE_UNDEFINED = 0
STATE_RUNNING   = 1
STATE_SLEEPING  = 2
STATE_WAITING   = 3
STATE_STOPPED   = 4
STATE_ZOMBIE    = 5

STATE_COLORS = [(0,0,0,0), PROC_COLOR_R, PROC_COLOR_S, PROC_COLOR_D, PROC_COLOR_T, PROC_COLOR_Z]

# Convert ps process state to an int
def get_proc_state(flag):
    return "RSDTZ".index(flag) + 1 

# Maximum time difference between two consecutive samples.  Anything more
# indicates an error.
MAX_SAMPLE_DIFF = 60000

# Maximum uptime for a sample.  Used to sanity check log file values and
# ignore inconsistent samples.
MAX_UPTIME =  1072911600000L # 30 years+ uptime

WHITE = (1.0, 1.0, 1.0, 1.0)

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
	
def draw_legend_box(ctx, label, fill_color, leg_x, leg_y, leg_s):
	draw_fill_rect(ctx, fill_color, (leg_x, leg_y - leg_s, leg_s, leg_s))
	draw_rect(ctx, PROC_BORDER_COLOR, (leg_x, leg_y - leg_s, leg_s, leg_s))
	draw_text(ctx, label, TEXT_COLOR, leg_x + leg_s + 5, leg_y)
     
def draw_legend_line(ctx, label, fill_color, leg_x, leg_y, leg_s):
	draw_fill_rect(ctx, fill_color, (leg_x, leg_y - leg_s/2, leg_s + 1, 3))    
	ctx.arc(leg_x + (leg_s + 1)/2.0, leg_y - (leg_s - 3)/2.0, 2.5, 0, 2.0 * math.pi)
	ctx.fill()
	draw_text(ctx, label, TEXT_COLOR, leg_x + leg_s + 5, leg_y)

def draw_label_centered(ctx, color, label, x, y, w):
	label_w = ctx.text_extents(label)[2]
	label_x = (x + w - label_w) / 2
	draw_text(ctx, label, color, label_x, y)

def draw_box_ticks(ctx, rect, sec_w, labels):
    if labels:
        ctx.set_font_size(AXIS_FONT_SIZE)

    draw_rect(ctx, BORDER_COLOR, (rect[0], rect[1], rect[2], rect[3]))

    for i in range(0, rect[2] + 1, sec_w):
        if ((i / sec_w) % 5 == 0) :
            if labels:
                label = "%ds" % (i / sec_w)
                label_width = ctx.text_extents(label)[2]
                draw_text(ctx, label, TEXT_COLOR, rect[0] + i - label_width/2, rect[1] - 2)
            ctx.set_source_rgba(*TICK_COLOR_BOLD)
        else :
            ctx.set_source_rgba(*TICK_COLOR)
        ctx.move_to(rect[0] + i, rect[1])
        ctx.line_to(rect[0] + i, rect[1] + rect[3])
        ctx.stroke()

def draw_chart(ctx, color, fill, chart_bounds, data_bounds, data):
    first = None
    last = None
    if data_bounds[2] == 0 or data_bounds[3] == 0:
        return
    xscale = float(chart_bounds[2])/data_bounds[2]
    yscale = float(chart_bounds[3])/data_bounds[3]
    ctx.save()
    ctx.translate(chart_bounds[0], chart_bounds[1] + chart_bounds[3])
    ctx.scale(1, -1)
    ctx.rectangle(0,0,chart_bounds[2],chart_bounds[3])
    ctx.clip()
    ctx.set_source_rgba(*color)
    for point in data:
        x = (point[0] - data_bounds[0]) * xscale
        y = (point[1] - data_bounds[1]) * yscale
        last = (x, y)
        if first is None:
            first = last
        ctx.line_to(last[0], last[1])
    if fill:
        ctx.stroke_preserve()
        ctx.line_to(last[0], 0)
        ctx.line_to(first[0], 0)
        ctx.line_to(first[0], first[1])
        ctx.fill()
    else:
        ctx.stroke()
    ctx.restore()
#
# Render the chart.
# 
def render(cairoContext, headers, cpu_stats, disk_stats, proc_tree):
    print 'proc_tree: num_proc=%i, duration=%i' % (proc_tree.num_proc, proc_tree.duration)
    header_h = 280
    bar_h = 55
    # offsets
    off_x = 10
    off_y = 10
		
    sec_w = 25 # the width of a second
    proc_h = 16 # the height of a process
    w = (proc_tree.duration * sec_w / 100) + 2*off_x
    h = proc_h * proc_tree.num_proc + header_h + 2*off_y
		
    if not cairoContext:
	surface = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    	ctx = cairo.Context(surface)
    else:
    	ctx = cairoContext
    	
    ctx.select_font_face(FONT_NAME)
    draw_fill_rect(ctx, WHITE, (0, 0, w, h))
    
    # draw the title and headers
    draw_header(ctx, headers, off_x, proc_tree.duration)

    rect_x = off_x
    rect_y = header_h + off_y
    rect_w = w - 2 * off_x
    rect_h = h - 2 * off_y - header_h
    
    # render bar legend
    ctx.set_font_size(LEGEND_FONT_SIZE)
    leg_y = rect_y - 2*bar_h - 6*off_y
    leg_x = off_x
    leg_s = 10
    if len(cpu_stats) > 0:
        draw_legend_box(ctx, "CPU (user+sys)", CPU_COLOR, leg_x, leg_y, leg_s)
        leg_x = leg_x + 120
        draw_legend_box(ctx, "I/O (wait)", IO_COLOR, leg_x, leg_y, leg_s)
        leg_x = leg_x + 120
				
    leg_x = off_x
    if len(disk_stats) > 0:
        leg_y = rect_y - bar_h - 4*off_y
        leg_x = off_x
        draw_legend_line(ctx, "Disk throughput", DISK_TPUT_COLOR, leg_x, leg_y, leg_s)
        leg_x = leg_x + 120
        draw_legend_box(ctx, "Disk utilization", IO_COLOR, leg_x, leg_y, leg_s)
        leg_x = leg_x + 120
		
    max_leg_x = leg_x

    # process states
    leg_y = rect_y - 17
    leg_x = off_x
    draw_legend_box(ctx, "Running (%cpu)", PROC_COLOR_R, leg_x, leg_y, leg_s)
    leg_x = leg_x + 120
		
    draw_legend_box(ctx, "Unint.sleep (I/O)", PROC_COLOR_D, leg_x, leg_y, leg_s)
    leg_x = leg_x + 120
		
    draw_legend_box(ctx, "Sleeping", PROC_COLOR_S, leg_x, leg_y, leg_s)
    leg_x = leg_x + 120
		
    draw_legend_box(ctx, "Zombie", PROC_COLOR_Z, leg_x, leg_y, leg_s)
    # leg_x += g.get_fontMetrics(LEGEND_FONT_SIZE).string_width(proc_z) + off_x
    leg_x = leg_x + 120

    print "start_time", proc_tree.start_time

    if len(cpu_stats) > 0:
	
        # render I/O wait
        bar_y = rect_y - 4*off_y - bar_h - off_x - 5;
        chart_rect = (rect_x, bar_y - bar_h, rect_w, bar_h)
        draw_box_ticks(ctx, chart_rect, sec_w, False)
        data_rect = (proc_tree.start_time, 0, proc_tree.duration, 1)
        draw_chart(ctx, IO_COLOR, True, chart_rect, data_rect, [(sample.time, sample.user + sample.sys + sample.io) for sample in cpu_stats]) 
        # render CPU load
        draw_chart(ctx, CPU_COLOR, True, chart_rect, data_rect, [(sample.time, sample.user + sample.sys) for sample in cpu_stats]) 
				
    if len(disk_stats) > 0:
        # render I/O utilization
        bar_y = rect_y - 2*off_y - off_y - 5
        chart_rect = (rect_x, bar_y - bar_h, rect_w, bar_h)
        draw_box_ticks(ctx, chart_rect, sec_w, False)
			
        data_rect = (proc_tree.start_time, 0, proc_tree.duration, 1)
        draw_chart(ctx, IO_COLOR, True, chart_rect, data_rect, [(sample.time, sample.util) for sample in disk_stats]) 
				
        # render disk throughput
        max_tput = max(sample.tput for sample in disk_stats)
        data_rect = (proc_tree.start_time, 0, proc_tree.duration, max_tput)
        draw_chart(ctx, DISK_TPUT_COLOR, False, chart_rect, data_rect, [(sample.time, sample.tput) for sample in disk_stats]) 

        for sample in disk_stats :
            # disk tput samples only
            if (sample.tput == max_tput) :
                pos_x = rect_x + ((sample.time - proc_tree.start_time) * rect_w / proc_tree.duration)
                if (pos_x < rect_x or pos_x > rect_x + rect_w) :
                    continue

                pos_y = bar_y -  (1.0 * bar_h)
                if (pos_x < max_leg_x) :
                    pos_y = pos_y + 15
                    pos_x = pos_x + 30
					
                label = "%dMB/s" % round((sample.tput) / 1024.0)
                draw_text(ctx, label, DISK_TPUT_COLOR, pos_x - 20, pos_y - 3)
		
                break

    if proc_tree.process_tree != None:
        # render processes
        
        draw_fill_rect(ctx, BACK_COLOR, (rect_x, rect_y, rect_w, rect_h))

        chart_rect = [rect_x, rect_y, rect_w, rect_h]
        draw_box_ticks(ctx, chart_rect, sec_w, True)	     		
        ctx.set_font_size(PROC_TEXT_FONT_SIZE)
        draw_process_list(ctx, proc_tree.process_tree, -1, -1, proc_tree, rect_y, proc_h, [rect_x, rect_y, rect_w, rect_h])

    ctx.set_font_size(SIG_FONT_SIZE)
    draw_text(ctx, SIGNATURE, SIG_COLOR, off_x + 5, h - off_y - 5)

    #surface.write_to_png(out_filename)

    return (0, 0, w,h)

def draw_header(ctx, headers, off_x, duration):
    dur = duration / 100.0
    toshow = [
      ('system.uname', 'uname', lambda s: s),
      ('system.release', 'release', lambda s: s),
      ('system.cpu', 'CPU', lambda s: re.sub('model name\s*:\s*', '', s, 1)),
      ('system.kernel.options', 'kernel options', lambda s: s),
      ('pseudo.header', 'time', lambda s: '%02d:%0.2f' % (math.floor(dur/60), dur - math.floor(dur/60)))
    ]

    header_y = ctx.font_extents()[2]
    header_y += 2
    ctx.set_font_size(TITLE_FONT_SIZE)
    draw_text(ctx, headers['title'], TEXT_COLOR, off_x, header_y)
    ctx.set_font_size(TEXT_FONT_SIZE)
	
    for (headerkey, headertitle, mangle) in toshow:
        header_y += ctx.font_extents()[2]
        txt = headertitle + ': ' + mangle(headers.get(headerkey))
        draw_text(ctx, txt, TEXT_COLOR, off_x, header_y)

def draw_process_list(ctx, process_list, px, py, proc_tree, y, proc_h, rect) :
    for proc in process_list:
#        print "proc '%s' with %i children" % (proc.cmd, len(proc.child_list))
        draw_process(ctx, proc, px, py, proc_tree, y, proc_h, rect)
        px2 = rect[0] +  ((proc.startTime - proc_tree.start_time) * rect[2] / proc_tree.duration)
        py2 = y + proc_h
        y = draw_process_list(ctx, proc.child_list, px2, py2, proc_tree, y + proc_h, proc_h, rect)
		
    return y
	
def draw_process(ctx, proc, px, py, proc_tree, y, proc_h, rect) :
#    print "drawing '%s'" % proc.cmd
    x = rect[0] +  ((proc.startTime - proc_tree.start_time) * rect[2] / proc_tree.duration)
    w =  ((proc.duration) * rect[2] / proc_tree.duration)
   
    draw_fill_rect(ctx, PROC_COLOR_S, (x, y, w, proc_h))

    ctx.set_source_rgba(*DEP_COLOR)
    if (px != -1 and py != -1) :
        if (abs(px - x) < 3) :
            dep_off_x = 3
            dep_off_y = proc_h / 4
            ctx.move_to(x, y + proc_h / 2)
            ctx.line_to(px - dep_off_x, y + proc_h / 2)
            ctx.line_to(px - dep_off_x, py - dep_off_y)
            ctx.line_to(px, py - dep_off_y)
        else :
            ctx.move_to(x, y + proc_h / 2)
            ctx.line_to(px, y + proc_h / 2)
            ctx.line_to(px, py)
               
    last_tx = -1
    for sample in proc.samples :
        end_time = proc.startTime + proc.duration - proc_tree.sample_period
        if sample.time < proc.startTime or sample.time > end_time :
            continue
                       
        tx = rect[0] + round(((sample.time - proc_tree.start_time) * rect[2] / proc_tree.duration))
        tw = round(proc_tree.sample_period * rect[2] / proc_tree.duration)
        if (last_tx != -1 and abs(last_tx - tx) <= tw) :
            tw -= last_tx - tx
            tx = last_tx
             
        last_tx = tx + tw
        state = get_proc_state( sample.state )
                   
        fill_rect = False
        if state in [STATE_WAITING, STATE_STOPPED, STATE_ZOMBIE]:
            color = STATE_COLORS[state]
            fill_rect = True
        elif state == STATE_RUNNING:
            cpu = sample.cpuSample.user + sample.cpuSample.sys
            alpha = (cpu * 255)
            alpha = max(0, min(alpha, 255))
            color = (PROC_COLOR_R[0], PROC_COLOR_R[1], PROC_COLOR_R[2], alpha)
            fill_rect = True
        else:
            fill_rect = False
                       
        if fill_rect:
            draw_fill_rect(ctx, color, (tx, y, tw, proc_h))
            
    draw_rect(ctx, PROC_BORDER_COLOR, (x, y, w, proc_h))
    draw_label_centered(ctx, PROC_TEXT_COLOR, proc.cmd, x, y + proc_h - 2, w)
