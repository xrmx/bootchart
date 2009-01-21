import gobject
import gtk
import gtk.gdk
import gtk.keysyms

import draw

class PyBootchartWidget(gtk.DrawingArea):
	__gsignals__ = {
		'expose-event': 'override',
		'clicked' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gtk.gdk.Event)),
		'position-changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_INT, gobject.TYPE_INT))
	}

	def __init__(self, res):
		gtk.DrawingArea.__init__(self)

		self.res = res

		self.set_flags(gtk.CAN_FOCUS)

                self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
                self.connect("button-press-event", self.on_area_button_press)
                self.connect("button-release-event", self.on_area_button_release)
                self.add_events(gtk.gdk.POINTER_MOTION_MASK | gtk.gdk.POINTER_MOTION_HINT_MASK | gtk.gdk.BUTTON_RELEASE_MASK)
                self.connect("motion-notify-event", self.on_area_motion_notify)
                self.connect("scroll-event", self.on_area_scroll_event)
                self.connect('key-press-event', self.on_key_press_event)

		self.zoom_ratio = 1.0
                self.x, self.y = 0.0, 0.0

	def do_expose_event(self, event):
		cr = self.window.cairo_create()

		# set a clip region for the expose event
		cr.rectangle(
			event.area.x, event.area.y,
			event.area.width, event.area.height
		)
		cr.clip()
		self.draw(cr, self.get_allocation())
		return False
		
	def draw(self, cr, rect):	
		cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
		cr.paint()
                cr.scale(self.zoom_ratio, self.zoom_ratio)
                cr.translate(-self.x, -self.y)
		self.boundingrect = draw.render(cr, *self.res)

	def position_changed(self):
		self.emit("position-changed", self.x, self.y)

	ZOOM_INCREMENT = 1.25

        def zoom_image(self, zoom_ratio):
            self.zoom_ratio = zoom_ratio
            self.queue_draw()

        def zoom_to_rect(self, rect):
            zoom_ratio = float(rect.width)/float(self.boundingrect[2])
            self.zoom_image(zoom_ratio)
	    self.x = 0
	    self.position_changed()

	def on_zoom_in(self, action):
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

	def on_zoom_out(self, action):
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

	def on_zoom_fit(self, action):		
            self.zoom_to_rect(self.get_allocation())

	def on_zoom_100(self, action):
            self.zoom_image(1.0)

        POS_INCREMENT = 100

        def on_key_press_event(self, widget, event):
                if event.keyval == gtk.keysyms.Left:
                        self.x -= self.POS_INCREMENT/self.zoom_ratio
                elif event.keyval == gtk.keysyms.Right:
                        self.x += self.POS_INCREMENT/self.zoom_ratio
                elif event.keyval == gtk.keysyms.Up:
                        self.y -= self.POS_INCREMENT/self.zoom_ratio
                elif event.keyval == gtk.keysyms.Down:
                        self.y += self.POS_INCREMENT/self.zoom_ratio
                elif event.keyval == gtk.keysyms.Page_Up:
                        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
                elif event.keyval == gtk.keysyms.Page_Down:
                        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
                else:
                        return False                
                self.queue_draw()
		self.position_changed()
                return True

        def on_area_button_press(self, area, event):
                if event.button == 2 or event.button == 1:
                        area.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.FLEUR))
                        self.prevmousex = event.x
                        self.prevmousey = event.y
                if event.type not in (gtk.gdk.BUTTON_PRESS, gtk.gdk.BUTTON_RELEASE):
                        return False
                return False

        def on_area_button_release(self, area, event):
                if event.button == 2 or event.button == 1:
                        area.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.ARROW))
                        self.prevmousex = None
                        self.prevmousey = None
                        return True
                return False

        def on_area_scroll_event(self, area, event):
                if event.direction == gtk.gdk.SCROLL_UP:
                        self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)
                        return True
                if event.direction == gtk.gdk.SCROLL_DOWN:
                        self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)
                        return True
                return False

        def on_area_motion_notify(self, area, event):
                state = event.state
                if state & gtk.gdk.BUTTON2_MASK or state & gtk.gdk.BUTTON1_MASK:
                        x, y = int(event.x), int(event.y)
                        # pan the image
                        self.x += (self.prevmousex - x)/self.zoom_ratio
                        self.y += (self.prevmousey - y)/self.zoom_ratio
                        self.queue_draw()
                        self.prevmousex = x
                        self.prevmousey = y
			self.position_changed()
                return True

class PyBootchartWindow(gtk.Window):

	ui = '''
	<ui>
		<toolbar name="ToolBar">
			<toolitem action="ZoomIn"/>
			<toolitem action="ZoomOut"/>
			<toolitem action="ZoomFit"/>
			<toolitem action="Zoom100"/>
		</toolbar>
	</ui>
	'''

	def __init__(self, res):
		gtk.Window.__init__(self)

		window = self
		window.connect("size-allocate", self.on_allocation_size_changed)

		window.set_title('Bootchart')
		window.set_default_size(512, 512)
		vbox = gtk.VBox()
		window.add(vbox)

		self.widget = PyBootchartWidget(res)
		self.widget.connect("position-changed", self.on_position_changed)

		self.extents = draw.extents(*res)

		# Create a UIManager instance
		uimanager = self.uimanager = gtk.UIManager()
		
		# Add the accelerator group to the toplevel window
		accelgroup = uimanager.get_accel_group()
		window.add_accel_group(accelgroup)

		# Create an ActionGroup
		actiongroup = gtk.ActionGroup('Actions')
		self.actiongroup = actiongroup

		# Create actions
		actiongroup.add_actions((
			('ZoomIn', gtk.STOCK_ZOOM_IN, None, None, None, self.widget.on_zoom_in),
			('ZoomOut', gtk.STOCK_ZOOM_OUT, None, None, None, self.widget.on_zoom_out),
			('ZoomFit', gtk.STOCK_ZOOM_FIT, 'Fit Width', None, None, self.widget.on_zoom_fit),
			('Zoom100', gtk.STOCK_ZOOM_100, None, None, None, self.widget.on_zoom_100),
		))

		# Add the actiongroup to the uimanager
		uimanager.insert_action_group(actiongroup, 0)

		# Add a UI description
		uimanager.add_ui_from_string(self.ui)

		# Scrollbars
		self.vadj = gtk.Adjustment()
		self.vadj.connect("value-changed", self.on_vertical_scroll_changed)

		self.hadj = gtk.Adjustment()
		self.hadj.connect("value-changed", self.on_horizontal_scroll_changed)

		hscrolled = gtk.HBox()
		vscrollbar = gtk.VScrollbar(self.vadj)
		hscrolled.pack_start(self.widget)
		hscrolled.pack_start(vscrollbar, False)

		vscrolled = gtk.VBox()
		hscrollbar = gtk.HScrollbar(self.hadj)
		vscrolled.pack_start(hscrolled)
		vscrolled.pack_start(hscrollbar, False)

		# Create a Toolbar
		toolbar = uimanager.get_widget('/ToolBar')
		vbox.pack_start(toolbar, False)
		vbox.pack_start(vscrolled)

		self.set_focus(self.widget)

		self.show_all()

	def on_allocation_size_changed(self, widget, allocation):
		self.update_scrollbars(self.widget.get_allocation())

	def update_scrollbars(self, rect):
		self.hadj.lower = 0
		self.hadj.upper = max(self.extents[0] - rect.width, 0)
		self.vadj.lower = 0
		self.vadj.upper = max(self.extents[1] - rect.height, 0)

	def on_vertical_scroll_changed(self, adj):
		self.widget.y = adj.value
		self.widget.queue_draw()

	def on_horizontal_scroll_changed(self, adj):
		self.widget.x = adj.value
		self.widget.queue_draw()

	def on_position_changed(self, widget, x, y):
		self.hadj.value = x
		self.vadj.value = y

def show(res):
	win = PyBootchartWindow(res)
	win.connect('destroy', gtk.main_quit)
	gtk.main()
