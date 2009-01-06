import sys
import gobject
import gtk
import gtk.gdk
import gtk.keysyms
import cairo
import pango
import pangocairo

import draw

class PyBootchartWidget(gtk.DrawingArea):
	__gsignals__ = {
		'expose-event': 'override',
		'clicked' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_STRING, gtk.gdk.Event))
	}

	def __init__(self):
		gtk.DrawingArea.__init__(self)

		self.set_flags(gtk.CAN_FOCUS)
                self.zoom_ratio = 1.0
		self.res = None

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
		self.boundingrect = draw.render(cr, *self.res)
	
	ZOOM_INCREMENT = 1.25

        def zoom_image(self, zoom_ratio):
            self.zoom_ratio = zoom_ratio
            self.queue_draw()

        def zoom_to_rect(self, rect):
            zoom_ratio = float(rect.width)/float(self.boundingrect[2])
            self.zoom_image(zoom_ratio)

	def on_zoom_in(self, action):
            self.zoom_image(self.zoom_ratio * self.ZOOM_INCREMENT)

	def on_zoom_out(self, action):
            self.zoom_image(self.zoom_ratio / self.ZOOM_INCREMENT)

	def on_zoom_fit(self, action):		
            self.zoom_to_rect(self.get_allocation())

	def on_zoom_100(self, action):
            self.zoom_image(1.0)

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

	def __init__(self):
		gtk.Window.__init__(self)

		window = self

		window.set_title('Bootchart')
		window.set_default_size(512, 512)
		vbox = gtk.VBox()
		window.add(vbox)

		self.widget = PyBootchartWidget()
		
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

		# Create a Toolbar
		toolbar = uimanager.get_widget('/ToolBar')
		vbox.pack_start(toolbar, False)
		vbox.pack_start(self.widget)

		self.set_focus(self.widget)

		self.show_all()

if __name__ == '__main__':
	import bc_parser
	res = bc_parser.parse_log_dir(sys.argv[1], True)
	win = PyBootchartWindow()
	win.connect('destroy', gtk.main_quit)
	win.widget.res = res
	gtk.main()
