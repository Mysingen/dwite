import os
import os.path
import traceback
import sys

from render  import TextRender
from display import TRANSITION

class Tree:
	label  = None
	parent = None
	render = None

	def __init__(self, label, parent):
		self.label  = label
		self.parent = parent
		self.render = TextRender('/Library/Fonts/Arial.ttf', 27)

	def __str__(self):
		return self.label
	
	def __cmp__(self, other):
		if self.label == other.label:
			return 0
		if self.label < other.label:
			return -1
		return 1

	def draw(self, canvas):
		return self.render.draw(canvas, self.label, 2)

	def tick(self, canvas):
		return self.render.tick(canvas)

class FileTree(Tree):
	path = None

	def __init__(self, label, parent, path):
		Tree.__init__(self, label, parent)
		self.path = path
		render = TextRender('/Library/Fonts/Times New Roman.ttf', 20)

	def play(self, player):
		return player.play_file(self.path)

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

class Menu:
	display = None # a Display instance that hides all device specific details
	root    = None # must always point to a Tree instance that implements ls()
	cwd     = None # must always point to a Tree instance that implements ls()
	current = 0    # index into cwd.children[]
	
	def __init__(self, display, root=None):
		self.display = display
		if not root:
			root = DirTree('/', None, os.getcwd())
		self.root = root
		self.cwd  = self.root
		self.cwd.ls()
		self.draw(TRANSITION.NONE)
	
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
			return TRANSITION.BOUNCE_LEFT
		self.cwd     = self.cwd.children[self.current]
		self.current = 0
		print 'enter %s' % str(self.cwd.path)
		return TRANSITION.SCROLL_LEFT

	def leave(self):
		try:
			self.cwd.parent.ls()
		except Exception, msg:
			return TRANSITION.BOUNCE_RIGHT
		self.current = self.cwd.parent.children.index(self.cwd)
		self.cwd     = self.cwd.parent
		print 'return %s' % str(self.cwd.path)
		return TRANSITION.SCROLL_RIGHT
	
	def up(self):
		if self.current > 0:
			self.current = self.current - 1
			return TRANSITION.SCROLL_DOWN
		return TRANSITION.BOUNCE_DOWN
	
	def down(self):
		if self.current < len(self.cwd.children) - 1:
			self.current = self.current + 1
			return TRANSITION.SCROLL_UP
		return TRANSITION.BOUNCE_UP

	def play(self, player):
		try:
			if self.cwd.children[self.current].play(player):
				# should temporarily replace the child with a PlayingTree object
				# that renders progress bars and stuff.
				return TRANSITION.NONE
		except:
			pass # no play() method or some other trouble.
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]

		return TRANSITION.BOUNCE_LEFT

	def draw(self, transition):
		if self.cwd.children[self.current].draw(self.display.canvas):
			self.display.show(transition)
	
	def tick(self):
		if self.cwd.children[self.current].tick(self.display.canvas):
			self.display.show(TRANSITION.NONE)
