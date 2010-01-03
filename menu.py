# -*- coding: utf-8 -*-

# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
import os.path
import traceback
import sys

import protocol

from render   import TextRender
from display  import TRANSITION
from tactile  import IR

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

class CmFileTree(Tree):
	cm = None

	def __init__(self, guid, label, parent, cm):
		Tree.__init__(self, guid, label, parent)
		self.cm = cm

class CmMp3Tree(CmFileTree):
	size   = 0   # bytes
	length = 0.0 # seconds

	def __init__(self, guid, label, size, length, parent, cm):
		CmFileTree.__init__(self, guid, label, parent, cm)
		self.size   = size
		self.length = length

class CmDirTree(CmFileTree):
	children = None

	def __init__(self, guid, label, parent, cm):
		CmFileTree.__init__(self, guid, label, parent, cm)
		self.render = TextRender('%s/fonts/LiberationSerif-Regular.ttf'
		                         % os.getenv('DWITE_HOME'), 23)
	
	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = [Waiting(self)]
		self.cm.wire.send(protocol.Ls(self.guid).serialize())
		# results will be added asynchronously
		return self.children

	def add(self, listing):
		if isinstance(self.children[0], Waiting):
			self.children = []
		for l in listing:
			guid  = l['guid']
			label = l['label']
			kind  = l['kind']

			if kind == 'dir':
				self.children.append(CmDirTree(guid, label, self, self.cm))
				continue

			if kind == 'file':
				self.children.append(CmFileTree(guid, label, self, self.cm))
				continue
			
			if kind == 'mp3':
				size   = l['size']
				length = l['length']
				self.children.append(
					CmMp3Tree(guid, label, size, length, self, self.cm)
				)

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

class Searcher(Tree):
	t9dict = None # {string:[strings]} to map digits to characters (T9 style)
	terms  = None # list of actual search terms
	render = None

	def __init__(self, guid, label, parent):
		Tree.__init__(self, guid, label, parent)
		self.children  = [Empty(self)]
		self.t9dict    = {}
		self.terms     = []
		self.last_code = None
		self.current   = None
		self.match     = ''
		self.candidates = None
		#self.render = ProgressRender()
	
	def add_dict_terms(self, terms):
		for t in terms:
			translation = list(t)
			for i in range(len(translation)):
				if translation[i] in list(
					u'1,;.:-_!\"@#£¤$%&/{([)]=}+?\\`\'^~*<>|§½€'
				):
					translation[i] = '1'
					continue
				if translation[i] in list(u'2abcåä'):
					translation[i] = '2'
					continue
				if translation[i] in list(u'3def'):
					translation[i] = '3'
					continue
				if translation[i] in list(u'4ghi'):
					translation[i] = '4'
					continue
				if translation[i] in list(u'5jkl'):
					translation[i] = '5'
					continue
				if translation[i] in list(u'6mnoö'):
					translation[i] = '6'
					continue
				if translation[i] in list(u'7pqrs'):
					translation[i] = '7'
					continue
				if translation[i] in list(u'8tuv'):
					translation[i] = '8'
					continue
				if translation[i] in list(u'9wxyz'):
					translation[i] = '9'
					continue
			translation = ''.join(translation)
			if translation not in self.t9dict:
				self.t9dict[translation] = [t]
			else:
				self.t9dict[translation].append(t)
	
	def set_search_terms(self, terms):
		self.terms = terms

	def consume(self, code):
		print 'consume %s' % IR.codes_debug[code]
		# build on the last item in the terms list until a space is seen.
		# then start a new search term unless space is given twice
		if code == self.last_code and code == IR.RIGHT:
			# two rights in a row terminates the terms list and run the search.
			print('search for %s' % self.terms)
			return True
		
		if code == IR.RIGHT:
			if self.current:
				self.terms.append(self.current)
				self.current = None
				self.match   = ''
				self.candidates = None
				print(' '.join(self.terms))
			return True
		
		if code == IR.LEFT:
			if len(self.match) > 0:
				self.match = self.match[:-1]
			return True
		
		if code in [IR.NUM_1, IR.NUM_2, IR.NUM_3,
		            IR.NUM_4, IR.NUM_5, IR.NUM_6,
		            IR.NUM_7, IR.NUM_8, IR.NUM_9]:
			self.match = self.match + IR.codes_debug[code]
			if not self.candidates:
				self.candidates = self.t9dict.keys()
			self.candidates = [c for c in self.candidates if c.startswith(self.match)]
			pretty = []
			for c in self.candidates:
				pretty.extend(self.t9dict[c])
			print('candidates: %s' % ' '.join(pretty))
			if len(self.candidates) > 0:
				self.current = self.candidates[0]
			return True


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
	root     = None # must always point to a Tree instance that implements ls()
	cwd      = None # must always point to a Tree instance that implements ls()
	current  = 0    # index into cwd.children[]
	searcher = None

	def __init__(self):
		self.root = Root()
		self.cwd  = self.root
		self.searcher = Searcher('Searcher', 'Search', self.root)
		self.root.add(self.searcher)

	def add_cm(self, cm):
		self.root.add(CmDirTree('/', cm.label, self.root, cm))

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

