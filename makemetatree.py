#!/usr/bin/env python
# Written by Chris Johnson
# Inspired by, and most of the heavy thinking done by:
#	Bram Cohen, John Hoffman

import sys
import getopt
import os
import sha
from copy import copy
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
		self.name = self.uniconvert(source,ENCODING)
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

	def uniconvertl(self, l, e):
		"""Convert a list of strings to Unicode

		Parameters
			str[]	Strings to be converted
			str	Current string encoding

		Return
			str[]	Converted strings"""
		r = []
		try:
			for s in l:
				r.append(self.uniconvert(s, e))
		except UnicodeError:
			raise UnicodeError('bad filename: '+os.path.join(l))
		return r
	
	def uniconvert(self, s, e):
		"""Convert a string to Unicode

		Parameters
			str	String to be converted
			str	Current string encoding

		Return
			str	Converted string"""
		try:
			s = unicode(s, e)
		except UnicodeError:
			raise UnicodeError('bad filename: '+s)
		return s.encode('utf-8')

	def add_file_info(self, size, path):
		"""Add file information to torrent.

		Parameters
			long size	- size of file (in bytes)
			str[] path	- file path (e.g. ['path','to','file.ext'])
		"""
		self.fs.append({'length': size, 'path': self.uniconvertl(path, ENCODING)})

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

# Recursive subfiles; gets file/directory structure and size in one go
def subfiles(n,p=[]):
	"""Get file/directory structure and size in one go

	Parameters
		str file	- Full file/directory name
		str[] path	- Target path

	Return
		str[] path	- Target path
		dirent		- Either full file/dir name OR
				  list of return tuples from this function
		int total	- Total size of file or subfiles"""
	if os.path.isdir(n):
		r=[]
		total = 0
		for s in sorted(os.listdir(n)):
			if s[0] == '.':
				continue
			r0 = subfiles(os.path.join(n, s), copy(p) + [s])
			r.append(r0)
			total += r0[2]
		return (p, r, total)

	size = os.path.getsize(n)
	return (p, n, size)

def traverse(arg,tracker,target,infolist=[]):
	"""Traverse a built file tree, constructing .torrent files at all levels
	
	Parameters
		tuple arg	- The output of a call to subfiles()
		str tracker	- Tracker for created .torrent files
		str target	- Current subtree (file/directory)
		Info[] infolist - Info objects to add current subtree to
	"""

	# p is path list (split at /)
	# d is either a file or a list of p,d,s tuples (a subtree)
	# s is the total size of the elements of d
	p,d,s = arg

	# p[0] is the base of the entire directory structure;
	# We want any .torrent file built to point to the same place
	info = Info(p[0],'/'.join([target]+p) + '.torrent',tracker,s)

	# Recurse if d is a directory
	if type(d) is type([]):
		print "Directory: %s/%s (%d)" % (target,'/'.join(p),s)
		os.makedirs('/'.join([target]+p))
		for i in d:
			traverse(i,tracker,target,infolist+[info])

	# Fill the info files with the data from this file
	else:
		print "File: %s:%s/%s.torrent (%d)" % (d,target,'/'.join(p),s)
		h = open(d,'rb')
		pos = 0L
		piece_length = 0
		for i in [info] + infolist:
			i.add_file_info(s,p[1:])
			if i.piece_length > piece_length:
				piece_length = i.piece_length

		while pos < s:
			a = min(piece_length, s - pos)
			buf = h.read(a)
			pos += a
			for i in [info] + infolist:
				i.add_data(buf)
			
	# We've either traversed or written a single full file, so
	# finish up.
	info.write()

def main(argv=None):
	if argv is None:
		argv = sys.argv
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hi:p:ut:", ["help","ignore-prefix=","prefix=","use-path","target="])
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
			print "Hopefully you're just me."
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
			if l <= len(path) and path[:l] = ignore:
				path = path[l:]

		p,r,t = subfiles(file,prefix + path + dirname)
		print "Total size: %d" % t
		traverse((p,r,t),tracker,target)

	return 0

if __name__ == '__main__':
	sys.exit(main())
