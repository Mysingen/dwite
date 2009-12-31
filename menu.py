# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
import os.path
import traceback
import sys

import protocol

from render  import TextRender
from display import TRANSITION

class Tree:
	guid     = None # string used when querying the CM for stats, listings, etc
	label    = None # string: the item's pretty printed identity
	parent   = None # another Tree node
	children = None # list of Tree nodes
	render   = None # Render object that knows how to draw this Tree node

	def __init__(self, guid, label, parent):
		self.guid   = guid
		self.label  = label
		self.parent = parent
		self.render = TextRender('%s/fonts/LiberationSerif-Regular.ttf'
		                         % os.getenv('DWITE_HOME'), 27)
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
	def __init__(self, guid, label, parent):
		Tree.__init__(self, guid, label, parent)

class DirTree(FileTree):
	children = None
	path     = None

	def __init__(self, guid, label, parent, path):
		if not os.path.isdir(path):
			raise Exception, 'DirTree(): %s is not a directory' % path
		FileTree.__init__(self, guid, label, parent)
		self.path   = path
		self.render = TextRender('%s/fonts/LiberationSans-Italic.ttf'
		                         % os.getenv('DWITE_HOME'), 20)

	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = []
		listing = os.listdir(self.path)
		listing.sort()
		for l in listing:
			path = os.path.join(self.path, l)
			if os.path.isdir(path):
				self.children.append(DirTree(l, l, self, path))
			else:
				self.children.append(FileTree(l, l, self))
		if len(self.children) == 0:
			self.children.append(Empty(self))
		return self.children

class Waiting(Tree):
	def __init__(self, parent):
		Tree.__init__(self, '<WAITING>', '<WAITING>', parent)

class CmDirTree(FileTree):
	children = None
	wire     = None

	def __init__(self, guid, label, parent, wire):
		FileTree.__init__(self, guid, label, parent)
		self.wire   = wire
		self.render = TextRender('%s/fonts/LiberationSerif-Regular.ttf'
		                         % os.getenv('DWITE_HOME'), 16)
	
	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = [Waiting(self)]
		self.wire.send(protocol.Ls(self.guid).serialize())
		# results will be added asynchronously
		return self.children

	def add(self, listing):
		if isinstance(self.children[0], Waiting):
			self.children = []
		for l in listing:
			if l[0] == 1:
				self.children.append(CmDirTree(l[1], l[2], self, self.wire))
			elif l[0] == 2:
				self.children.append(FileTree(l[1], l[2], self))
		if len(self.children) == 0:
			self.children.append(Empty(self))
		return self.children


class Empty(Tree):
	def __init__(self, parent):
		Tree.__init__(self, '<EMPTY>', '<EMPTY>', parent)

class Playlist(Tree):
	def __init__(self, parent):
		Tree.__init__(self, 'Playlist', 'Playlist', parent)
		self.children = [Empty(self)]

	def add(self, item):
		print('Playlist add %s' % item)
		if isinstance(self.children[0], Empty):
			self.children = []
		self.children.append(item)

	def remove(self, item):
		print('Playlist remove %s' % item)
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
		Tree.__init__(self, '/', '/', None)
		self.playlist = Playlist(self)
		self.children = []
		self.children.append(self.playlist)
		self.children.append(
			DirTree('Browse files', 'Browse files', self, os.getcwd())
		)

	def add(self, item):
		if isinstance(item, Tree):
			print('Root add %s' % item)
			self.children.append(item)
		else:
			print('Will not add non-Tree object to Root: %s' % item)

class Menu:
	root    = None # must always point to a Tree instance that implements ls()
	cwd     = None # must always point to a Tree instance that implements ls()
	current = 0    # index into cwd.children[]

	def __init__(self):
		self.root = Root()
		self.cwd  = self.root
		self.cwd.ls()

	def add_cm(self, label, wire):
		self.root.add(CmDirTree('/', label, self.root, wire))

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

