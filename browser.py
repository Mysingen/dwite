import os
import os.path

class Tree:
	label  = None
	parent = None

	def __init__(self, label, parent):
		self.label  = label
		self.parent = parent

	def __str__(self):
		return self.label
	
	def __cmp__(self, other):
		if self.label == other.label:
			return 0
		if self.label < other.label:
			return -1
		return 1

class FileTree(Tree):
	path = None
	
	def __init__(self, label, parent, path):
		Tree.__init__(self, label, parent)
		self.path = path

class DirTree(FileTree):
	children = []

	def __init__(self, label, parent, path):
		FileTree.__init__(self, label, parent, path)
		
		if not os.path.isdir(self.path):
			raise Exception, 'DirTree(): %s is not a directory' % path

	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = []
		listing = os.listdir(self.path)
		listing.sort()
		for l in listing:
			path = os.path.join(self.path, l)
			if os.path.isdir(path):
				self.children.append(DirTree(l, self, path))
			else:
				self.children.append(FileTree(l, self, path))
		if len(self.children) == 0:
			self.children.append(Tree('<EMPTY>', self))
		return self

class Browser:
	root    = None # must always point to a Tree instance that implements ls()
	cwd     = None # must always point to a Tree instance that implements ls()
	current = 0 # index into cwd.children[]
	
	def __init__(self, root):
		self.root = root
		self.cwd  = self.root
		self.cwd.ls()
	
	def __str__(self):
		return str(self.cwd.children[self.current])
	
	def dump(self):
		print self.cwd
		print self.current
		for f in self.cwd:
			print '\t' + str(f)
	
	def enter(self):
		try:
			self.cwd.children[self.current].ls()
		except Exception, msg:
			# self.current has no listable content and can thus not be entered
			return False
		self.cwd     = self.cwd.children[self.current]
		self.current = 0
		print 'enter %s' % str(self.cwd.path)
		return True

	def leave(self):
		try:
			self.cwd.parent.ls()
		except Exception, msg:
			return False
		self.current = self.cwd.parent.children.index(self.cwd)
		self.cwd     = self.cwd.parent
		print 'return %s' % str(self.cwd.path)
		return True
	
	def up(self):
		if self.current > 0:
			self.current = self.current - 1
			return True
		return False
	
	def down(self):
		if self.current < len(self.cwd.children) - 1:
			self.current = self.current + 1
			return True
		return False

