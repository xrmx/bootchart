from distutils.core import setup

idStr = '$Id$'

setup(name = 'pybootchartgui',
      version = 'r' + idStr.split()[2],
      description = 'Python bootchart graph utility',

      packages = ['pybootchartgui'],
      package_dir = {'pybootchartgui': 'pybootchartgui'},

      scripts = ['pybootchartgui.py'],
      )

