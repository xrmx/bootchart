from distutils.core import setup
from os import environ

if 'PKG_VER' in environ:
    VERSION = environ['PKG_VER']
else:
    VERSION = ''
  

setup(name = 'pybootchartgui',
      version = VERSION,
      description = 'Python bootchart graph utility',
      url = 'http://github.com/mmeeks/bootchart/',

      maintainer = 'Michael Meeks',
      maintainer_email = 'michael.meeks@novell.com',

      packages = ['pybootchartgui'],
      package_dir = {'pybootchartgui': 'pybootchartgui'},

      scripts = ['pybootchartgui.py'],
      )

