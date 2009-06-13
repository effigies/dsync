#!/usr/bin/env python
# Written by Chris Johnson
# Inspired by, and most of the heavy thinking done by:
#	Bram Cohen, John Hoffman

import sys
import getopt
import os
import sha
from BitTornado.bencode import bencode
from BitTornado.BT1.btformats import check_info
from threading import Event
from time import time
from traceback import print_exc
try:
	ENCODING = sys.getfilesystemencoding()
except:
	ENCODING = sys.getdefaultencoding()
	if not ENCODING:
		ENCODING = 'ascii'


# Generic utility functions
def uniconvertl(srclist, encoding):
	"""Convert a list of strings to Unicode

	Parameters
		str[]	- Strings to be converted
		str	- Current string encoding

	Return
		str[]	- Converted strings
	"""
	r = []
	try:
		for src in srclist:
			r.append(uniconvert(src, encoding))
	except UnicodeError:
		raise UnicodeError('bad filename: '+os.path.join(srclist))
	return r

def uniconvert(src, encoding):
	"""Convert a string to Unicode

	Parameters
		str	- String to be converted
		str	- Current string encoding

	Return
		str	- Converted string
	"""
	try:
		return unicode(src, encoding).encode('utf-8')
	except UnicodeError:
		raise UnicodeError('bad filename: ' + src)

class Info:
	"""Info - information associated with a .torrent file

	Info attributes
		str target		- absolute path of target .torrent file
		long size		- total size of files to be described
		long piece_length	- size of pieces
		str[] pieces		- sha1 digests of file parts
		sha1 HASH sh		- sha1 hash object
		long done		- portion of piece hashed
		dict[] fs		- metadata about files described
		long totalhashed	- portion of total data hashed
	"""

	def __init__(self,source,target,tracker,size):
		"""
		Parameters
			str source	- source file name (last path element)
			str target	- target file name (full path)
			str tracker	- URL of tracker
			int size	- total size of files to be described
		"""
		self.name = uniconvert(source,ENCODING)
		self.target = target
		self.tracker = tracker
		self.size = size
		self.piece_length = self.get_piece_len(size)
		self.pieces = []
		self.sh = sha.sha()
		self.done = 0L
		self.fs = []
		self.totalhashed = 0L

	def get_piece_len(self,size): 
		"""Parameters
			int size	- size of files to be described by torrent

		Return
			int		- size of pieces to hash
		"""
		if   size > 8L*1024*1024*1024:	# > 8 gig =
			piece_len_exp = 21	#   2 meg pieces
		elif size > 2*1024*1024*1024:	# > 2 gig =
			piece_len_exp = 20	#   1 meg pieces
		elif size > 512*1024*1024:	# > 512M =
			piece_len_exp = 19	#   512K pieces
		elif size > 64*1024*1024:	# > 64M =
			piece_len_exp = 18	#   256K pieces
		elif size > 16*1024*1024:	# > 16M =
			piece_len_exp = 17	#   128K pieces
		elif size > 4*1024*1024:	# > 4M =
			piece_len_exp = 16	#   64K pieces
		else:				# < 4M =
			piece_len_exp = 15	#   32K pieces
		return 2 ** piece_len_exp


	def add_file_info(self, size, path):
		"""Add file information to torrent.

		Parameters
			long size	- size of file (in bytes)
			str[] path	- file path (e.g. ['path','to','file.ext'])
		"""
		self.fs.append({'length': size, 'path': uniconvertl(path, ENCODING)})

	def add_data(self, data):
		"""Process a segment of data.

		Note that the sequence of calls to this function is sensitive to
		order and concatenation. Treat it as a rolling hashing function, as
		it uses one.
		
		The length of data is relatively unimportant, though exact multiples
		of piece_length will slightly improve performance. The largest
		possible piece_length (2**21 bytes == 2MB) would be a reasonable
		default.
		
		Parameters
			str data	- an arbitrarily long segment of the file to
					  be hashed
		"""
		while len(data) > 0:
			a = len(data)
			r = self.piece_length - self.done
			if a < r:
				self.sh.update(data)
				self.done += a
				self.totalhashed += a
				break
			else:
				d = data[:r]
				data = data[r:]
				self.sh.update(d)
				self.pieces.append(self.sh.digest())
				self.done = 0
				self.sh = sha.sha()

	def write(self):
		"""Write a .torrent file"""

		# Whatever hash we have left, we'll take
		if self.done > 0:
			self.pieces.append(self.sh.digest())

		info = {'pieces': ''.join(self.pieces),
			'piece length': self.piece_length,
			'files': self.fs,
			'name': self.name}

		check_info(info)

		data = {'info': info, 'announce': self.tracker, 'creation data': long(time())}

		h = open(self.target, 'wb')
		h.write(bencode(data))
		h.close()

class BTTree:
	def __init__(self, loc, path = []):
		self.loc = os.path.abspath(loc)
		self.path = path
		if os.path.isfile(loc):
			self.subs = None
			self.size = os.path.getsize(loc)
		elif os.path.isdir(loc):
			self.subs = []
			for sub in sorted(os.listdir(self.loc)):
				if sub[0] == '.':
					continue
				sloc = os.path.join(loc,sub)
				spath = self.path + [sub]
				try:
					self.subs.append(BTTree(sloc,spath))
				except problem:
					print problem

			self.size = sum([sub.size for sub in self.subs])
		else:
			raise Exception("Entry is neither file nor directory: %s"
				% loc)

	def buildMetaTree(self, tracker, target, infolist = []):
		info = Info(	self.path[0],
				os.path.join(target, *self.path) + '.torrent',
				tracker,
				self.size)

		infos = infolist + [info]

		if self.subs is not None:
			for sub in self.subs:
				sub.buildMetaTree(tracker, target, infos)

		else:
			h = open(self.loc,'rb')
			pos = 0L
			piece_length = max([i.piece_length for i in infos])

			while pos < self.size:
				a = min(piece_length, self.size - pos)
				buf = h.read(a)
				pos += a
				[i.add_data(buf) for i in infos]

		target_dir = os.path.split(info.target)[0]
		if not os.path.exists(target_dir):
			os.makedirs(target_dir)
		info.write()

def main(argv):
	help = """Usage: %s [OPTIONS] TRACKER [DIRS]
Build a meta-tree of each directory in DIRS
When DIRS is a single file, behaves essentially like btmakemetafile.

	--help		display this help and exit
	--use-path	use the path as given in the .torrent files
	--prefix	prepend some path info in .torrent files
	--ignore-prefix	ignore part of path (implies --use-path)
	--target	build meta-tree elsewhere than in the source directory
	""" % argv[0].split('/')[-1]

	if len(argv) == 1:
		print help
		return 1

	try:
		opts, args = getopt.getopt(argv[1:], "hi:p:ut:",
			["help","ignore-prefix=","prefix=","use-path","target="])
	except getopt.error, msg:
		print msg
		return 0

	u = False	# Use the actual path in the torrent files
	prefix = []	# Prepend directories to path in torrents
	ignore = []	# Ignore path elements at the beginning
	target = ''	# Target directory tree in which to store torrent files

	# Parse arguments
	for opt, arg in opts:
		if opt in ('-h','--help'):
			print help
			return 0
		elif opt in ('-u','--use-path'):
			u = True
		elif opt in ('-p','--prefix'):
			arg = arg.strip('/')
			prefix = arg.split('/')
		elif opt in ('-i','--ignore-prefix'):
			u = True
			arg = arg.strip('/')
			ignore = arg.split('/')
		elif opt in ('-t','--target'):
			if arg[:1] not in ['/','~']:
				arg = './' + arg
			target = arg

	tracker = args.pop(0)

	for arg in args:
		file = arg

		arg = arg.strip('/')

		path = []
		dirname = arg.split('/')[-1:]

		# Using path
		if u:
			path = arg.split('/')[:-1]

			# Try to ignore some initial path elements
			l = len(ignore)
			if l <= len(path) and path[:l] == ignore:
				path = path[l:]

		tree = BTTree(file, prefix + path + dirname)
		tree.buildMetaTree(tracker,target)

	return 0

if __name__ == '__main__':
	sys.exit(main(sys.argv))
