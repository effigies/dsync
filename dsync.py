#!/usr/bin/env python
import sys
import os
import re
from makemetatree import BTTree

def init(args):
	if args == []:
		source = os.getcwd()
	
	else:
		source = os.path.abspath(args.pop(0))

	target = os.path.join(source,".dsync")

	

def main(argv):
	name = re.sub("dsync-?","",os.path.split(argv.pop(0))[1])
	if re.match("^(.py)?$",name):
		name = argv.pop(0)

	if name == "init":
		return init(argv)

if __name__ == '__main__':
	sys.exit(main(sys.argv))
