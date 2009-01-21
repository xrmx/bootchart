import cairo

import draw

def render(res, format, filename):
    handlers = {
        "png": (lambda (w,h): cairo.ImageSurface(cairo.FORMAT_ARGB32,w,h), lambda sfc: sfc.write_to_png(filename)),
        "pdf": (lambda (w,h): cairo.PDFSurface(filename, w, h), lambda sfc: 0),
        "svg": (lambda (w,h): cairo.SVGSurface(filename, w, h), lambda sfc: 0)
    }

    if not(handlers.has_key(format)):
        print "Unknown format '%s'." % format
        return 10

    mk, cl = handlers[format]
    w,h = draw.extents(*res)
    surface = mk((w,h))
    ctx = cairo.Context(surface)
    draw.render(ctx, *res)
    cl(surface)

