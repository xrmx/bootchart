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

import gobject
import gtk
import gtk.gdk
import gtk.keysyms
import math
from . import draw
from .draw import DrawContext

class PyBootchartWidget(gtk.DrawingArea):
    __gsignals__ = {
            'expose-event': 'override',
            'clicked' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gtk.gdk.Event)),
            'position-changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_INT, gobject.TYPE_INT)),
            'set-scroll-adjustments' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gtk.Adjustment, gtk.Adjustment))
    }

    def __init__(self, trace, drawctx, xscale):
        gtk.DrawingArea.__init__(self)

        self.trace = trace
        self.drawctx = drawctx

        self.set_flags(gtk.CAN_FOCUS)

        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
        self.connect("button-press-event", self.on_area_button_press)
        self.connect("button-release-event", self.on_area_button_release)
        self.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
        self.connect("motion-notify-event", self.on_area_motion_notify)
        self.connect("scroll-event", self.on_area_scroll_event)
        self.connect('key-press-event', self.on_key_press_event)

        self.connect('set-scroll-adjustments', self.on_set_scroll_adjustments)
        self.connect("size-allocate", self.on_allocation_size_changed)
        self.connect("position-changed", self.on_position_changed)

        self.zoom_ratio = 1.0
        self.xscale = xscale
        self.x, self.y = 0.0, 0.0

        self.chart_width, self.chart_height = draw.extents(self.drawctx, self.xscale, self.trace)
        self.hadj = None
        self.vadj = None
        self.hadj_changed_signal_id = None
        self.vadj_changed_signal_id = None

        self.sweep_csec = None

        self.hide_process_y = []         # XX  valid only between self.on_area_button_press() and self.draw()

    def do_expose_event(self, event):    # XX called on mouse entering or leaving window -- can these be disabled?
        cr = self.window.cairo_create()
        self.draw(cr)
        return False

    def cr_set_up_transform(self, cr):
        cr.scale(self.zoom_ratio, self.zoom_ratio)
        cr.translate(-self.x, -self.y)

    def draw(self, cr):
        cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
        cr.paint()                               # fill whole DrawingArea with white
        self.cr_set_up_transform(cr)
        draw.render(cr, self.drawctx, self.xscale, self.trace,
                    list(self.sweep_csec) if self.sweep_csec else None, # pass by value not ref
                    self.hide_process_y)
        self.hide_process_y = []

    def position_changed(self):
        self.emit("position-changed", self.x, self.y)

    def device_to_csec_user_y(self, dx, dy):
            cr = self.window.cairo_create()
            self.cr_set_up_transform(cr)   # depends on (self.x, self.y)
            ux, uy = cr.device_to_user(dx, dy)
            #self.chart_width, self.chart_height = draw.extents(self.drawctx, self.xscale, self.trace)
            return draw._xscaled_to_csec(ux,
                                          draw._sec_w(self.xscale),
                                          draw._time_origin_drawn(self.drawctx, self.trace)), \
                   uy

    # back-transform center of widget to (time, chart_height) coords
    def current_center (self):
        (wx, wy, ww, wh) = self.get_allocation()
        return self.device_to_csec_user_y (ww/2, wh/2)

    # Assuming all object attributes except self.x and self.y are now valid,
    # and that a new zoom_ratio or xscale has been set, correspondingly
    # set top-left user-space corner position (self.x, self.y) so that
    # (csec_x, user_y) will be at window center
    def set_center (self, ctr_csec_x, ctr_user_y):
        ctr_user_x = draw.C.off_x + draw._csec_to_xscaled(ctr_csec_x,
                                       draw._time_origin_drawn(self.drawctx, self.trace),
                                       draw._sec_w(self.xscale))
        # XX Use cr.device_to_user_distance() here ?
        # Subtract off from the center a vector to the top-left corner.
        self.x = (ctr_user_x - float(self.get_allocation()[2])/self.zoom_ratio/2)
        self.y = (ctr_user_y - float(self.get_allocation()[3])/self.zoom_ratio/2)
        self.position_changed()

    ZOOM_INCREMENT = 2
    ZOOM_HALF_INCREMENT = math.sqrt(2)
    # Zoom maintaining the content at window's current center untranslated.
    # "Center" is irrespective of any occlusion.
    def zoom_image (self, zoom_ratio):
        old_csec, old_y = self.current_center ()

        self.zoom_ratio = zoom_ratio

        self.set_center(old_csec, old_y)
        self._set_scroll_adjustments (self.hadj, self.vadj)
        self.queue_draw()

    def zoom_to_rect (self, rect):       #  rename "zoom_to_window_width"?
        zoom_ratio = float(rect.width)/float(self.chart_width)
        self.zoom_image(zoom_ratio)
        self.x = 0
        self.position_changed()

    def set_xscale(self, xscale):
        old_csec, old_y = self.current_center ()

        self.xscale = xscale
        self.chart_width, self.chart_height = draw.extents(self.drawctx, self.xscale, self.trace)

        self.set_center(old_csec, old_y)
        self._set_scroll_adjustments (self.hadj, self.vadj)
        self.queue_draw()

    def on_expand(self, action):
        self.set_xscale (self.xscale * 1.1)

    def on_contract(self, action):
        self.set_xscale (self.xscale / 1.1)

    def on_zoom_in(self, action):
        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

    def on_zoom_out(self, action):
        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

    def on_zoom_fit(self, action):
        self.zoom_to_rect(self.get_allocation())

    def on_zoom_100(self, action):
        self.zoom_image(1.0)  # XX  replace with:   self.zoom_ratio = 1.0  \  self.x = 0  \  self.y = 0
        self.set_xscale(1.0)

    def absolute_uptime_event_times(self, action, current):
        self.drawctx.app_options.absolute_uptime_event_times = action.get_current_value()
        self.queue_draw()

    def show_IO_ops(self, action, current):
        self.drawctx.app_options.show_ops_not_bytes = action.get_current_value()
        self.queue_draw()

    def show_thread_details(self, action):
        self.drawctx.app_options.show_all = action.get_active()
        self.queue_draw()

    def hide_events(self, action):
        self.drawctx.app_options.hide_events = not action.get_active()
        self.queue_draw()

    def print_event_times(self, action):
        self.drawctx.app_options.print_event_times = action.get_active()
        self.queue_draw()

    def event_source_toggle(self, action):
        # turn second char of the string into an int
        self.drawctx.app_options.event_source[int(action.get_name()[1])].enable = action.get_active()
        self.drawctx.ps_event_lists_valid = False
        self.queue_draw()

    def _toggle_EventColor_by_label(self, ecl, action):
        for ec in ecl:
            if ec.label == action.get_name():
                break
        ec.enable = action.get_active()
        self.drawctx.ps_event_lists_valid = False
        self.queue_draw()

    def event_toggle(self, action):
        self._toggle_EventColor_by_label(
            self.drawctx.app_options.event_color, action)

    def event_interval_toggle(self, action):
        self._toggle_EventColor_by_label(
            self.drawctx.app_options.event_interval_color, action)

    def dump_raw_event_context(self, action):
        self.drawctx.app_options.dump_raw_event_context = action.get_active()
        self.queue_draw()

    def show_legends(self, action):
        self.drawctx.app_options.show_legends = action.get_active()
        self.queue_draw()

    POS_INCREMENT = 100

    # file:///usr/share/doc/libgtk2.0-doc/gtk/GtkWidget.html says:
    #     Returns :
    #        TRUE to stop other handlers from being invoked for the event.
    #        FALSE to propagate the event further
    def on_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Left:
            self.x -= self.POS_INCREMENT/self.zoom_ratio
        elif event.keyval == gtk.keysyms.Right:
            self.x += self.POS_INCREMENT/self.zoom_ratio
        elif event.keyval == gtk.keysyms.Up:
            self.y -= self.POS_INCREMENT/self.zoom_ratio
        elif event.keyval == gtk.keysyms.Down:
            self.y += self.POS_INCREMENT/self.zoom_ratio
        else:
            return False
        #self.queue_draw()
        self.position_changed()
        return True

    def on_area_button_press(self, area, event):
        # cancel any pending action based on an earlier button pressed and now held down
        self.hide_process_y = []

        if event.button == 1:
            area.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.FLEUR))
            self.prevmousex = event.x
            self.prevmousey = event.y
        elif event.button == 2 and len(self.hide_process_y) == 0:
            self.hide_process_y.append( self.device_to_csec_user_y(event.x, event.y)[1])
        elif event.button == 3:
            if not self.sweep_csec:
                self.sweep_csec = [self.device_to_csec_user_y(event.x, 0)[0],
                                   self.device_to_csec_user_y(self.trace.end_time, 0)[0]]
            else:
                self.sweep_csec = None
            self.queue_draw()
        if event.type not in (gtk.gdk.BUTTON_PRESS, gtk.gdk.BUTTON_RELEASE):
            return False
        return True

    def on_area_button_release(self, area, event):
        if event.button == 1:
            area.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.ARROW))
            self.prevmousex = None
            self.prevmousey = None
            return True
        elif event.button == 2 and len(self.hide_process_y) == 1:
            self.hide_process_y.append( self.device_to_csec_user_y(event.x, event.y)[1])
            self.queue_draw()
        elif event.button == 3:
            if self.sweep_csec and \
                   self.sweep_csec[1] != self.device_to_csec_user_y(self.trace.end_time, 0)[0]:
                    self.drawctx.event_dump_list = []    # XX
            self.queue_draw()
        return True

    def on_area_scroll_event(self, area, event):
        if event.state & gtk.gdk.CONTROL_MASK:
            if event.direction == gtk.gdk.SCROLL_UP:
                self.on_expand(None)
                return True
            if event.direction == gtk.gdk.SCROLL_DOWN:
                self.on_contract(None)
                return True
        elif event.state & gtk.gdk.MOD1_MASK:
            if event.direction == gtk.gdk.SCROLL_UP:
                self.zoom_image(self.zoom_ratio * self.ZOOM_HALF_INCREMENT)
                return True
            if event.direction == gtk.gdk.SCROLL_DOWN:
                self.zoom_image(self.zoom_ratio / self.ZOOM_HALF_INCREMENT)
                return True

    def on_area_motion_notify(self, area, event):
        state = event.state
        if state & gtk.gdk.BUTTON1_MASK:
            x, y = int(event.x), int(event.y)
            if self.prevmousex==None or self.prevmousey==None:
                return True
            # pan the image
            self.x += (self.prevmousex - x)/self.zoom_ratio
            self.y += (self.prevmousey - y)/self.zoom_ratio
            self.prevmousex = x
            self.prevmousey = y
            self.position_changed()
        elif state & gtk.gdk.BUTTON3_MASK and self.sweep_csec:
            self.sweep_csec[1] = self.device_to_csec_user_y(event.x, 0)[0]
            #self.queue_draw()
        return True

    def on_set_scroll_adjustments(self, area, hadj, vadj):
        self._set_scroll_adjustments (hadj, vadj)

    def on_allocation_size_changed(self, widget, allocation):
        self.hadj.page_size = allocation.width
        self.hadj.page_increment = allocation.width * 0.9
        self.vadj.page_size = allocation.height
        self.vadj.page_increment = allocation.height * 0.9

    def _set_adj_upper(self, adj, upper):
        changed = False
        value_changed = False

        if adj.upper != upper:
            adj.upper = upper
            changed = True

        max_value = max(0.0, upper - adj.page_size)
        if adj.value > max_value:
            adj.value = max_value
            value_changed = True

        if changed:
            adj.changed()
        if value_changed:
            adj.value_changed()

    # sets scroll bars to correct position and length -- no direct effect on image
    def _set_scroll_adjustments(self, hadj, vadj):
        if hadj == None:
            hadj = gtk.Adjustment(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        if vadj == None:
            vadj = gtk.Adjustment(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        if self.hadj_changed_signal_id != None and \
           self.hadj != None and hadj != self.hadj:
            self.hadj.disconnect (self.hadj_changed_signal_id)
        if self.vadj_changed_signal_id != None and \
           self.vadj != None and vadj != self.vadj:
            self.vadj.disconnect (self.vadj_changed_signal_id)

        if hadj != None:
            self.hadj = hadj
            self._set_adj_upper (self.hadj, self.zoom_ratio * self.chart_width)
            self.hadj_changed_signal_id = self.hadj.connect('value-changed', self.on_adjustments_changed) # XX  leaky?

        if vadj != None:
            self.vadj = vadj
            self._set_adj_upper (self.vadj, self.zoom_ratio * self.chart_height)
            self.vadj_changed_signal_id = self.vadj.connect('value-changed', self.on_adjustments_changed)

    def on_adjustments_changed(self, adj):
        self.x = self.hadj.value / self.zoom_ratio
        self.y = self.vadj.value / self.zoom_ratio
        self.queue_draw()

    def on_position_changed(self, widget, x, y):
        self.hadj.value = x * self.zoom_ratio
        self.vadj.value = y * self.zoom_ratio

PyBootchartWidget.set_set_scroll_adjustments_signal('set-scroll-adjustments')

class PyBootchartShell(gtk.VBox):
    def __init__(self, window, trace, drawctx, xscale):
        gtk.VBox.__init__(self)

        self.widget = PyBootchartWidget(trace, drawctx, xscale)

        # Create a UIManager instance
        uimanager = self.uimanager = gtk.UIManager()

        uimanager.add_ui_from_string('''
        <ui>
            <toolbar name="ToolBar">
                    <toolitem action="Expand"/>
                    <toolitem action="Contract"/>
                    <separator/>
                    <toolitem action="ZoomIn"/>
                    <toolitem action="ZoomOut"/>
                    <toolitem action="ZoomFit"/>
                    <toolitem action="Zoom100"/>
            </toolbar>
            <menubar name="MenuBar">
                <menu action="Time">
                    <menuitem action="bootchart daemon start"/>
                    <menuitem action="system boot"/>
                </menu>
                <menu action="I/O">
                    <menuitem action="hardware operations"/>
                    <menuitem action="512-byte sectors"/>
                </menu>
            </menubar>
        </ui>
        ''')

        actiongroup = gtk.ActionGroup('Actions')

        # Zooming buttons
        actiongroup.add_actions((
            ('Expand', gtk.STOCK_ORIENTATION_LANDSCAPE, None, None, "widen", self.widget.on_expand),
            ('Contract', gtk.STOCK_ORIENTATION_PORTRAIT, None, None, "narrow", self.widget.on_contract),
            ('ZoomIn', gtk.STOCK_ZOOM_IN, None, None, "zoom in", self.widget.on_zoom_in),
            ('ZoomOut', gtk.STOCK_ZOOM_OUT, None, None, "zoom out", self.widget.on_zoom_out),
            ('ZoomFit', gtk.STOCK_ZOOM_FIT, 'Fit Width', None, "zoom-to-fit while preserving aspect ratio", self.widget.on_zoom_fit),
            ('Zoom100', gtk.STOCK_ZOOM_100, None, None, "zoom to best image quality", self.widget.on_zoom_100),
        ))

        # "Time" drop-down menu
        actiongroup.add_radio_actions([
            ("bootchart daemon start", None, "bootchart daemon start -- startup of the collector daemon on the target", None, None, False),
            ("system boot", None, "system boot i.e. 'uptime'", None, None, True),
            ], 1 if drawctx.app_options.absolute_uptime_event_times else 0, self.widget.absolute_uptime_event_times
        )
        actiongroup.add_actions((
            ("Time", None, "Time", None, "XXX why does this not show up???  time-origin selection for display"),
        ))

        # I/O dropdown
        actiongroup.add_radio_actions([
            ("hardware operations", None, "hardware operations", None, None, True),
            ("512-byte sectors", None, "512-byte sectors", None, None, False),
            ], drawctx.app_options.show_ops_not_bytes, self.widget.show_IO_ops
        )
        actiongroup.add_actions((
            ("I/O", None, "I/O", None, ""),
        ))

        # Threads dropdown
        if not drawctx.kernel_only:
            uimanager.add_ui_from_string('''
            <ui>
                <menubar name="MenuBar">
                    <menu action="Threads">
                        <menuitem action="details"/>
                    </menu>
                </menubar>
            </ui>
            ''')
            actiongroup.add_toggle_actions([
                ('details', None, "details", None, None, self.widget.show_thread_details, drawctx.app_options.show_all),
            ])
            actiongroup.add_actions([
                ("Threads", None, "Threads", None, ""),
            ])


        # Events dropdown
        ui_Events = '''
        <ui>
            <menubar name="MenuBar">
                <menu action="Events">
                    <menuitem action="show"/>
                    <menuitem action="times"/>
                </menu>
            </menubar>
        </ui>
        '''
        actiongroup.add_toggle_actions([
            ('show', None, "show", None, None, self.widget.hide_events, not drawctx.app_options.hide_events),
            ('times', None, "show times", None, None, self.widget.print_event_times, drawctx.app_options.print_event_times),
        ])
        uimanager.add_ui_from_string(ui_Events)
        actiongroup.add_actions([
            ("Events", None, "Events", None, ""),
        ])


        # Event Source dropdown
        ui_Event_Source = '''
        <ui>
            <menubar name="MenuBar">
                <menu action="Event_Source">
        '''
        def add_es(index, es, callback):
            action_name = "p{0:d}".format(index)  # callback will extract a list index from this name string
                                                  # XX Supports 10 logs, max
            actiongroup.add_toggle_actions([
                (action_name, None,
                 "{0:s} ({1:d})".format(es.label, len(es.parsed)),
                 None, None,
                 getattr(self.widget, callback), es.enable),
            ])
            return '''
                    <menuitem action="{0:s}"/>
            '''.format(action_name)

        for index, es in enumerate(drawctx.app_options.event_source):
            ui_Event_Source += add_es(index, es, "event_source_toggle")
        ui_Event_Source += '''
                </menu>
            </menubar>
        </ui>
        '''
        uimanager.add_ui_from_string(ui_Event_Source)
        actiongroup.add_actions([
            ("Event_Source", None, "Ev-Sources", None, ""),
        ])


        # Event Color dropdown
        ui_Event_Color = '''
        <ui>
            <menubar name="MenuBar">
                <menu action="Event_Color">
        '''
        def add_re(ec, callback_name):
            # XX  add_toggle_actions() can take a "user_data" arg -- but how is the value
            #     retrieved later?
            actiongroup.add_toggle_actions([
                (ec.label, None, ec.label, None, None,
                 getattr(self.widget, callback_name), ec.enable),
            ])
            return '''
                    <menuitem action="{0:s}"/>
            '''.format(ec.label)
        for ec in drawctx.app_options.event_color:
            ui_Event_Color += add_re(ec, "event_toggle")
        ui_Event_Color += '''<separator/>'''

        for ec in drawctx.app_options.event_interval_color:
            ui_Event_Color += add_re(ec, "event_interval_toggle")
        ui_Event_Color += '''
                </menu>
            </menubar>
        </ui>
        '''
        uimanager.add_ui_from_string(ui_Event_Color)
        actiongroup.add_actions([
            ("Event_Color", None, "Ev-Color", None, ""),
        ])

        # Stdout, Help dropdowns
        uimanager.add_ui_from_string( '''
        <ui>
            <menubar name="MenuBar">
                <menu action="Stdout">
                    <menuitem action="dump raw"/>
                </menu>
                <menu action="Help">
                    <menuitem action="show legends"/>
                </menu>
            </menubar>
        </ui>
        ''')
        # Stdout dropdown
        actiongroup.add_toggle_actions([
            ('dump raw', None, "dump raw context lines from log along with events", None, None,
             self.widget.dump_raw_event_context, drawctx.app_options.dump_raw_event_context),
        ])
        actiongroup.add_actions([
            ("Stdout", None, "Stdout", None, ""),
        ])

        # Stdout dropdown
        actiongroup.add_toggle_actions([
            ('show legends', None, "show legends", None, None,
             self.widget.show_legends, drawctx.app_options.show_legends),
        ])
        actiongroup.add_actions([
            ("Help", None, "Help", None, ""),
        ])

        uimanager.insert_action_group(actiongroup, 0)

        # toolbar / h-box
        hbox = gtk.HBox(False, 0)

        # Create a Toolbar
        toolbar = uimanager.get_widget('/ToolBar')
        hbox.pack_start(toolbar, True)

        menubar = uimanager.get_widget("/MenuBar")
        hbox.pack_start(menubar, True)

        # force all the real widgets to the left
        #  XX Why doesn't this force the others all the way to the left?
        empty_menubar = gtk.MenuBar()
        hbox.pack_start(empty_menubar, True, True)

        self.pack_start(hbox, False)

        # Scrolled window
        scrolled = gtk.ScrolledWindow()
        scrolled.add(self.widget)

        self.pack_start(scrolled)
        self.show_all()

    def grab_focus(self, window):
        window.set_focus(self.widget)


class PyBootchartWindow(gtk.Window):

    def __init__(self, app_options, trace):
        gtk.Window.__init__(self)

        window = self
        window.set_title("Bootchart %s" % trace.filename)
        screen = window.get_screen()
        window.set_default_size(screen.get_width() * 95/100,
                                screen.get_height() * 95/100)

        full_drawctx = DrawContext(app_options, trace)
        full_tree = PyBootchartShell(window, trace, full_drawctx,
                                     # XX  "1.7" is a hack
                                     float(window.get_default_size()[0]) * 1.7 / \
                                     ((trace.end_time - trace.start_time) + \
                                      2 * trace.ps_stats.sample_period))
        # FIXME: Permanently disable top-level tabs?
        if True:
            window.add(full_tree)
        else:
            tab_page = gtk.Notebook()
            tab_page.show()
            window.add(tab_page)

            tab_page.append_page (full_tree, gtk.Label("Full tree"))

            if trace.kernel is not None and len (trace.kernel) > 2:
                kernel_drawctx = DrawContext(app_options, trace, cumulative = False, charts = False, kernel_only = True)
                kernel_tree = PyBootchartShell(window, trace, kernel_drawctx, 5.0)
                tab_page.append_page (kernel_tree, gtk.Label("Kernel boot"))

        full_tree.grab_focus(self)
        self.show()


def show(trace, app_options):
    win = PyBootchartWindow(app_options, trace)
    win.connect('destroy', gtk.main_quit)
    gtk.main()
