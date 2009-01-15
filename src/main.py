import sys
import os

import parsing
import gui

sys.path.insert(0, os.getcwd())

if __name__ == '__main__':
	res = parsing.parse_log_dir(sys.argv[1], True)
        gui.show(res)
