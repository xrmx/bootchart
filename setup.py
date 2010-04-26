from distutils.core import setup

setup(name = 'pybootchartgui',
      description = 'Python bootchart graph utility',

      packages = ['pybootchartgui'],
      package_dir = {'pybootchartgui': 'pybootchartgui'},

      scripts = ['pybootchartgui.py'],
      )

