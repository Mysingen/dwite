# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
import os.path
import traceback
import sys

from render  import TextRender
from display import TRANSITION

class Tree:
	guid     = None # string
	label    = None # string: the item's pretty printed identity
	parent   = None # another Tree node
	children = None # list of Tree nodes
	render   = None # Render object that knows how to draw this Tree node

	def __init__(self, label, parent):
		self.guid   = label # FIXME
		self.label  = label
		self.parent = parent
		self.render = TextRender('fonts/LiberationSerif-Regular.ttf', 27)
		self.render.curry(self.label)

	def __str__(self):
		return self.label
	
	def __cmp__(self, other):
		if self.guid == other.guid:
			return 0
		if self.guid < other.guid:
			return -1
		return 1

	def curry(self):
		self.render.curry(self.label)
		return (self.guid, self.render)

	def ticker(self):
		return (self.guid, self.render)

	def ls(self):
		return self.children

class FileTree(Tree):
	def __init__(self, label, parent, path):
		Tree.__init__(self, label, parent)
		self.guid = path

class DirTree(FileTree):
	children = []

	def __init__(self, label, parent, path):
		FileTree.__init__(self, label, parent, path)
		self.render = TextRender('fonts/LiberationSans-Italic.ttf', 20)

		if not os.path.isdir(self.guid):
			raise Exception, 'DirTree(): %s is not a directory' % path

	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = []
		listing = os.listdir(self.guid)
		listing.sort()
		for l in listing:
			path = os.path.join(self.guid, l)
			if os.path.isdir(path):
				self.children.append(DirTree(l, self, path))
			else:
				self.children.append(FileTree(l, self, path))
		if len(self.children) == 0:
			self.children.append(Empty(self))
		return self

class Empty(Tree):
	def __init__(self, parent):
		Tree.__init__(self, '<EMPTY>', parent)

class Playlist(Tree):
	def __init__(self, parent):
		Tree.__init__(self, 'Playlist', parent)
		self.children = [Empty(self)]

	def add(self, item):
		print('add %s' % item)
		if isinstance(self.children[0], Empty):
			self.children = []
		self.children.append(item)

	def remove(self, item):
		print('remove %s' % item)
		try:
			index = self.children.index(item)
			del self.children[index]
			if len(self.children) == 0:
				self.children = [Empty(self)]
		except:
			print('Could not remove %s' % item)
			pass
		

# specialty class to hold the menu system root node
class Root(Tree):
	playlist = None

	def __init__(self):
		Tree.__init__(self, '/', None)
		self.playlist = Playlist(self)
		self.children = []
		self.children.append(self.playlist)
		self.children.append(DirTree('Browse files', self, os.getcwd()))

class Menu:
	root    = None # must always point to a Tree instance that implements ls()
	cwd     = None # must always point to a Tree instance that implements ls()
	current = 0    # index into cwd.children[]

	def __init__(self):
		self.root = Root()
		self.cwd  = self.root
		self.cwd.ls()

	def enter(self):
		if self.focused().ls():
			self.cwd     = self.focused()
			self.current = 0
			print 'enter %s' % str(self.cwd.guid)
			transition = TRANSITION.SCROLL_LEFT
		else:
			# self.current has no listable content and can thus not be entered
			transition = TRANSITION.BOUNCE_LEFT
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def leave(self):
		if self.cwd.parent:
			self.cwd.parent.ls()
			self.current = self.cwd.parent.children.index(self.cwd)
			self.cwd     = self.cwd.parent
			print 'return %s' % str(self.cwd.guid)
			transition = TRANSITION.SCROLL_RIGHT
		else:
			transition = TRANSITION.BOUNCE_RIGHT
		(guid, render) = self.focused().curry()
		return (guid, render, transition)
	
	def up(self):
		if self.current > 0:
			self.current = self.current - 1
			transition = TRANSITION.SCROLL_DOWN
		else:
			transition = TRANSITION.BOUNCE_DOWN
		(guid, render) = self.focused().curry()
		return (guid, render, transition)
	
	def down(self):
		if self.current < len(self.cwd.children) - 1:
			self.current = self.current + 1
			transition = TRANSITION.SCROLL_UP
		else:
			transition = TRANSITION.BOUNCE_UP
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def ticker(self, curry=False):
		if curry:
			(guid, render) = self.focused().curry()
		else:
			(guid, render) = self.focused().ticker()
		return (guid, render)

	def focused(self):
		if self.current + 1 >= len(self.cwd.children):
			# item has disappeared. e.g. when an item is removed from playlist
			self.current = len(self.cwd.children) - 1
		return self.cwd.children[self.current]

	def playlist(self):
		return self.root.playlist

