# -*- coding: utf-8 -*-

# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
import os.path
import traceback
import sys
import random

import protocol

from render   import SearchRender, ItemRender
from display  import TRANSITION
from tactile  import IR

class Tree(object):
	guid     = None # string used when querying the CM for stats, listings, etc
	label    = None # string: the item's pretty printed identity
	parent   = None # another Tree node
	children = None # list of Tree nodes
	render   = None # Render object that knows how to draw this Tree node

	def __init__(self, guid, label, parent):
		assert type(label) == unicode
		self.guid   = guid
		self.label  = label
		self.parent = parent
		self.render = ItemRender('%s/fonts/LiberationSerif-Regular.ttf'
		                         % os.getenv('DWITE_HOME'), 27, (2, 0))

	def __str__(self):
		return 'Tree %s %s' % (self.guid, self.label)
	
	def __cmp__(self, other):
		if self.guid == other.guid:
			return 0
		if self.guid < other.guid:
			return -1
		return 1

	def __eq__(self, other):
		if not other:
			return False
		if type(self) != type(other):
			return False
		return self.guid == other.guid

	def __ne__(self, other):
		return not self.__eq__(other)

	def get_pretty(self):
		return self.label

	def curry(self):
		self.render.curry(self)
		return (self.guid, self.render)

	def ticker(self):
		return (self.guid, self.render)

	def ls(self):
		return self.children
	
	def next(self, wrap=False, rand=False):
		if not self.parent:
			return None
		try:
			if rand:
				index = random.randint(0, len(self.parent.children)-1)
			else:
				index = self.parent.children.index(self) + 1
				if wrap:
					index %= len(self.parent.children)
			return self.parent.children[index]
		except:
			return None

	def prev(self, wrap=False, rand=False):
		if not self.parent:
			return None
		try:
			if rand:
				index = random.randint(0, len(self.parent.children)-1)
			else:
				index = self.parent.children.index(self) - 1
				if wrap:
					index %= len(self.parent.children)
				elif index < 0:
					return None
			return self.parent.children[index]
		except:
			return None

	def is_parent_of(self, other):
		while other.parent:
			if other.parent.guid == self.guid:
				return True
			other = other.parent

class Waiting(Tree):
	def __init__(self, parent):
		Tree.__init__(self, u'<WAITING>', u'<WAITING>', parent)

class Error(Tree):
	def __init__(self, message, parent):
		Tree.__init__(self, u'<ERROR>', message, parent)

class CmFile(Tree):
	cm_label = None

	def __init__(self, guid, label, parent, cm):
		assert type(cm) == unicode
		Tree.__init__(self, guid, label, parent)
		self.cm_label = cm

	@property
	def cm(self):
		from dwite import get_cm
		return get_cm(self.cm_label)

class CmAudio(CmFile):
	size     = 0 # bytes
	duration = 0 # milliseconds
	format   = None # 'mp3' or 'flac'
	artist   = None
	album    = None
	title    = None
	n        = None

	def __init__(
		self, guid, label, artist, album, title, n, size, duration, format,
		parent, cm
	):
		if type(size) != int:
			raise Exception(
				'CmAudio.size != int: %s (guid:%s)' % (str(size), guid)
			)
		if type(duration) != int:
			raise Exception(
				'CmAudio.duration != int: %s (guid:%s)' % (str(duration), guid)
			)
		if format not in ['mp3', 'flac']:
			raise Exception(
				'Invald CmAudio.format: %s (guid:%s)' % (str(format), guid)
			)
		assert artist == None or type(artist) == unicode
		assert album  == None or type(album)  == unicode
		assert title  == None or type(title)  == unicode
		assert n      == None or type(n)      == unicode
		CmFile.__init__(self, guid, label, parent, cm)
		self.size     = size
		self.duration = duration
		self.format   = format
		self.artist   = artist
		self.album    = album
		self.title    = title
		self.n        = n

	def __str__(self):
		return 'CmAudio %s %s %s %s %s %s' % (
			self.guid, self.label, self.artist, self.album, self.title, self.n
		)
	
	def get_pretty(self):
		pretty = self.label # a safe default, but try to improve it:
		if self.title:
			pretty = self.title
			if self.album:
				pretty += ' / ' + self.album
			if self.artist:
				pretty += ' / ' + self.artist
		return pretty

class CmDir(CmFile):
	children = None

	def __init__(self, guid, label, parent, cm):
		CmFile.__init__(self, guid, label, parent, cm)
		self.render = ItemRender('%s/fonts/LiberationSerif-Regular.ttf'
		                         % os.getenv('DWITE_HOME'), 23, (2, 0))
	
	def __iter__(self):
		return self.children.__iter__()

	def ls(self):
		self.children = [Waiting(self)]
		return self.children

	def add(self, listing):
		if (not self.children) or (isinstance(self.children[0], Waiting)):
			self.children = []
		for l in listing:
			guid  = l['guid']
			label = l['pretty']['label']
			kind  = l['kind']

			if kind == 'dir':
				self.children.append(CmDir(guid, label, self, self.cm_label))
				continue

			if kind == 'file':
				self.children.append(CmFile(guid, label, self, self.cm_label))
				continue
			
			if kind in ['mp3', 'flac']:
				size     = l['size']
				duration = l['duration']
				pretty   = l['pretty']
				self.children.append(
					CmAudio(
						guid, label, pretty['artist'], pretty['album'],
						pretty['title'], pretty['n'], size, duration, kind,
						self, self.cm_label
					)
				)
				continue
			
		if len(self.children) == 0:
			self.children.append(Empty(self))
		return self.children

class Empty(Tree):
	def __init__(self, parent):
		Tree.__init__(self, u'<EMPTY>', u'<EMPTY>', parent)

class Link(Tree):
	target = None # Tree object

	def __init__(self, target, parent):
		assert isinstance(target, Tree)
		guid = ''.join([unicode(random.randint(0,9)) for i in range(32)])
		Tree.__init__(self, guid, target.label, parent)
		self.target = target

	def get_pretty(self):
		return self.target.get_pretty()

class Playlist(Tree):
	def __init__(self, parent):
		Tree.__init__(self, u'Playlist', u'Playlist', parent)
		self.children = [Empty(self)]

	def add(self, item):
		if not isinstance(item, CmAudio):
			return
		print('Playlist add %s' % item)
		if isinstance(self.children[0], Empty):
			self.children = []
		self.children.append(Link(item, self))

	def remove(self, item):
		if type(item) == Empty:
			return
		assert type(item) == Link
		print('Playlist remove %s' % item.target)
		try:
			index = self.children.index(item)
			del self.children[index]
			if len(self.children) == 0:
				self.children = [Empty(self)]
		except:
			print('Could not remove %s' % item)
			pass

	def dump(self):
		result = []
		if type(self.children[0]) == Empty:
			return result
		for link in self.children:
			item = link.target
			obj = {}
			obj['cm']     = item.cm_label
			obj['guid']   = item.guid
			obj['pretty'] = {
				'label' : item.label,
				'artist': item.artist,
				'album' : item.album,
				'title' : item.title,
				'n'     : item.n
			}
			obj['kind']   = item.format
			if item.format in ['mp3', 'flac']:
				obj['size'] = item.size
				obj['duration'] = item.duration
			result.append(obj)
		return result

class CandidateTree(Tree):
	query = None

	def __init__(self, label, parent, query):
		Tree.__init__(self, u'CandidateTree', label, parent)
		self.query  = query
		self.render = SearchRender()
		self.render.curry(self.label, query)

	def __str__(self):
		return "%s (query = %s)" % (self.label, self.query)
	
	def __cmp__(self, other):
		if self.guid == other.guid:
			return 0
		if self.guid < other.guid:
			return -1
		return 1

	def curry(self):
		self.render.curry(self.label, self.query)
		return (self.guid, self.render)

	def ticker(self):
		return (self.guid, self.render)

class Searcher(Tree):
	t9dict = None # {string:[strings]} to map digits to characters (T9 style)
	term   = None # string of numbers the user has pressed to form a word
	render = None
	query  = None # list of actual search terms

	def __init__(self, guid, label, parent):
		Tree.__init__(self, guid, label, parent)
		self.t9dict   = {}
		self.term     = '' # search term built in T9 style (digits only)
		self.query    = [] # all built search terms (translated strings)
		label         = (u'<Type to get suggestions. UP/DOWN adds/removes '
		              +   'suggestions, LEFT/RIGHT navigates suggestions>')
		self.children = [CandidateTree(label, self, self.get_query())]

		self.candidates  = None # T9 encoded search term suggestions
		self.suggestions = None # plain text search term suggestions
		self.index       = 0

	def dump(self):
		return {
			'term'       : self.term,
			'query'      : self.query,
			'suggestions': self.suggestions,
			'index'      : self.index
		}

	def get_query(self):
		if self.query:
			return u' '.join(self.query)
		return u'<NO TERMS ADDED>'
	
	def add_terms(self, cm, terms):
		#print 'add search terms: %s' % terms
		for t in terms:
			# make a char list from each term so we can change single entries
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
			# change the translation from char list to string again:
			translation = ''.join(translation)
			if translation not in self.t9dict:
				self.t9dict[translation] = set()
			self.t9dict[translation].add(t)
	
	def make_suggestions(self):
		self.suggestions = []
		self.candidates = [
			k for k in self.t9dict.keys() if k.startswith(self.term)
		]
		
		tmp_1 = []
		for c in self.candidates:
			tmp_1.extend(self.t9dict[c])
		# sort the suggestions so that all words with one char appear first,
		# followed by all words with two chars, et.c. Don't do more than 20
		# words (to keep down CPU usage).
		tmp_2 = {}
		count = 0
		for s in tmp_1:
			if len(s) not in tmp_2:
				tmp_2[len(s)] = [s]
			else:
				tmp_2[len(s)].append(s)

			count = count + 1
			if count == 20:
				break
		# we now have a dict with suggestions sorted into different "length
		# buckets". go through them from shortest to longest and build the
		# final list of suggestions.
		keys = tmp_2.keys()
		keys.sort()
		for i in keys:
			p = tmp_2[i]
			p.sort()
			self.suggestions.extend(p)

	def right(self):
		#print 'right + %s' % self.dump()
		# if there are suggestions, increase the suggestion index and redraw:
		if self.suggestions:
			if self.index < len(self.suggestions) - 1:
				self.index += 1
				transition = TRANSITION.NONE
			else:
				transition = TRANSITION.BOUNCE_LEFT
			label = u' '.join(self.suggestions[self.index:])
		else:
			label      = u''
			transition = TRANSITION.BOUNCE_LEFT
		self.children = [CandidateTree(label, self, self.get_query())]
		return transition

	def left(self):
		#print 'left + %s' % self.dump()
		# if a search is running, return to the query construction widget:
		if self.children[0].label == u'<SEARCHING>':
			self.term  = u''
			label      = (u'<Type to get suggestions. UP/DOWN adds/removes '
			           +   'suggestions, LEFT/RIGHT navigates suggestions>')
			transition = TRANSITION.SCROLL_RIGHT
		# if there are suggestions, decrease the suggestion index and redraw:
		elif self.suggestions and self.index > 0:
			self.index -= 1
			transition  = TRANSITION.NONE
			label       = u' '.join(self.suggestions[self.index:])
		# if a term is under construction, reduce it by one character:
		elif self.term:
			self.term  = self.term[:-1]
			transition = TRANSITION.NONE
			self.index = 0
			if self.term:
				self.make_suggestions()
				label = u' '.join([s for s in self.suggestions])
			else:
				label = u''
		# remove the last term in the query, if any:
		elif self.query:
			self.query = self.query[:-1]
			transition = TRANSITION.NONE
			if self.query:
				label = u''
			else:
				label = (u'<Type to get suggestions. UP/DOWN adds/removes '
				      +   'suggestions, LEFT/RIGHT navigates suggestions>')
		# leave the widget (by throwing an exception) if there is no query
		# and no search term under construction:
		else:
			label = (u'<Type to get suggestions. UP/DOWN adds/removes '
			      +   'suggestions, LEFT/RIGHT navigates suggestions>')
			self.children = [CandidateTree(label, self, self.get_query())]
			raise Exception('The user has left the widget')
		self.children = [CandidateTree(label, self, self.get_query())]
		return transition

	def up(self):
		#print 'up + %s' % self.dump()
		# if there are suggestions, add the indexed one to the query:
		if self.suggestions:
			self.query.append(self.suggestions[self.index])
			self.term        = u''
			self.candidates  = None
			self.suggestions = None
			self.index       = 0
			label            = u''
			self.children = [CandidateTree(label, self, self.get_query())]
			transition = TRANSITION.NONE
		else:
			transition = TRANSITION.BOUNCE_DOWN
		return transition

	def down(self):
		#print 'down + %s' % self.dump()
		# if there are terms in the query, remove the last one:
		if self.query:
			self.query = self.query[:-1]
			label = (u'<Type to get suggestions. UP/DOWN adds/removes '
			      +   'suggestions, LEFT/RIGHT navigates suggestions>')
			self.children = [CandidateTree(label, self, self.get_query())]
			transition = TRANSITION.NONE
		else:
			transition = TRANSITION.BOUNCE_UP
		return transition

	def number(self, code):
		if code not in [IR.NUM_0, IR.NUM_1, IR.NUM_2, IR.NUM_3, IR.NUM_4,
		                IR.NUM_5, IR.NUM_6, IR.NUM_7, IR.NUM_8, IR.NUM_9]:
			raise Exception('Unknown numeric code: %d' % code)
		#print '%s + %s' % (IR.codes_debug[code], self.dump())
		self.term += IR.codes_debug[code]
		self.make_suggestions()
		if self.suggestions:
			self.index = 0
			label      = u' '.join([s for s in self.suggestions])
			transition = TRANSITION.NONE
		else:
			self.term  = self.term[:-1]
			self.make_suggestions()
			label      = u' '.join(self.suggestions[self.index:])
			transition = TRANSITION.BOUNCE_LEFT
		self.children = [CandidateTree(label, self, self.get_query())]
		return transition

	def play(self):
		print 'play + %s' % self.dump()
		if self.query:
			self.children = [
				CandidateTree(u'<SEARCHING>', self, self.get_query())
			]
			return TRANSITION.SCROLL_LEFT
		return TRANSITION.BOUNCE_LEFT


# specialty class to hold the menu system root node
class Root(Tree):
	def __init__(self):
		Tree.__init__(self, u'/', u'/', None)
		self.children = []

	def __eq__(self, other):
		if not other:
			return False
		# use object id's for important singleton items instead of string
		# comparison on guid's which could give false positives:
		return id(self) == id(other)

	def __ne__(self, other):
		return not self.__eq__(other)

	def add(self, item):
		if isinstance(item, Tree):
			#print('Root add %s' % item)
			self.children.append(item)
		else:
			print('Will not add non-Tree object to Root: %s' % item)

	def remove(self, item):
		#print('Root remove %s' % item)
		try:
			index = self.children.index(item)
			del self.children[index]
			if len(self.children) == 0:
				self.children = [Empty(self)]
		except:
			print('Could not remove %s' % item)
			pass

class Menu:
	root     = None # must always point to a Tree instance that implements ls()
	cwd      = None # must always point to a Tree instance that implements ls()
	current  = 0    # index into cwd.children[]
	searcher = None

	def __init__(self):
		self.root = Root()
		self.cwd  = self.root
		self.searcher = Searcher(u'Searcher', u'Search', self.root)
		self.playlist = Playlist(self.root)
		self.root.add(self.playlist)
		self.root.add(self.searcher)

	def add_cm(self, cm):
		self.root.add(CmDir(u'/', cm.label, self.root, cm.label))

	def rem_cm(self, cm):
		focused = self.focused()
		removed = CmDir(u'/', cm.label, self.root, cm.label)
		self.root.remove(removed)
		if removed.is_parent_of(focused):
			self.cwd     = self.root
			self.current = 0

	def right(self):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.right()
			except:
				traceback.print_exc()
				self.set_focus(self.searcher)
				transition = TRANSITION.SCROLL_RIGHT
		elif self.focused().ls():
			self.cwd     = self.focused()
			self.current = 0
			#print 'enter %s' % str(self.cwd.guid)
			transition = TRANSITION.SCROLL_LEFT
		else:
			# self.current has no listable content and can thus not be entered
			transition = TRANSITION.BOUNCE_LEFT
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def left(self):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.left()
			except:
				traceback.print_exc()
				self.set_focus(self.searcher)
				transition = TRANSITION.SCROLL_RIGHT
		elif self.cwd.parent:
			self.current = self.cwd.parent.children.index(self.cwd)
			self.cwd     = self.cwd.parent
			#print 'return %s' % str(self.cwd.guid)
			transition = TRANSITION.SCROLL_RIGHT
		else:
			transition = TRANSITION.BOUNCE_RIGHT
		(guid, render) = self.focused().curry()
		return (guid, render, transition)
	
	def up(self):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.up()
			except:
				traceback.print_exc()
				self.set_focus(self.searchar)
				transition = TRANSITION.SCROLL_RIGHT
		elif self.current > 0:
			self.current = self.current - 1
			transition = TRANSITION.SCROLL_DOWN
		else:
			transition = TRANSITION.BOUNCE_DOWN
		(guid, render) = self.focused().curry()
		return (guid, render, transition)
	
	def down(self):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.down()
			except:
				traceback.print_exc()
				self.set_focus(self.searcher)
				transition = TRANSITION.SCROLL_RIGHT
		elif self.current < len(self.cwd.children) - 1:
			self.current = self.current + 1
			transition = TRANSITION.SCROLL_UP
		else:
			transition = TRANSITION.BOUNCE_UP
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def number(self, ir_code):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.number(ir_code)
			except:
				traceback.print_exc()
				self.set_focus(self.searcher)
				transition = TRANSITION.SCROLL_RIGHT
		else:
			transition = TRANSITION.NONE
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def play(self):
		if self.cwd == self.searcher:
			try:
				transition = self.searcher.play()
			except:
				traceback.print_exc()
				self.set_focus(self.searcher)
				transition = TRANSITION.SCROLL_RIGHT
		else:
			transition = TRANSITION.BOUNCE_LEFT
		(guid, render) = self.focused().curry()
		return (guid, render, transition)

	def next_render_mode(self):
		(guid, render) = self.focused().ticker()
		render.next_mode()

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

	def set_focus(self, item):
		# set cwd to the parent of the item. unparented items raise exception.
		# set the current index by looking for the item in cwd.
		if item.parent:
			self.cwd = item.parent
			self.current = self.cwd.children.index(item)
		else:
			raise Exception('Can only focus items with parents')

	def get_item(self, label):
		for c in self.root.children:
			if c.label == label:
				return c
		return None

# create an item. the new item is not parented!
def make_item(cm, guid, pretty, kind, size=0, duration=0):
	assert type(cm)       == unicode
	assert type(guid)     == unicode
	assert type(size)     == int
	assert type(duration) == int
	assert 'label' in pretty and type(pretty['label']) == unicode
	assert kind in ['dir', 'file', 'mp3', 'flac']

	if kind == 'dir':
		return CmDir(guid, pretty['label'], None, cm)

	if kind == 'file':
		return CmFile(guid, pretty['label'], None, cm)

	if kind in ['mp3', 'flac']:
		artist = None
		if 'artist' in pretty:
			artist = pretty['artist']
		album = None
		if 'album' in pretty:
			album = pretty['album']
		title = None
		if 'title' in pretty:
			title = pretty['title']
		n = None
		if 'n' in pretty:
			n = pretty['n']
		return CmAudio(
			guid, pretty['label'], artist, album, title, n, size, duration,
			kind, None, cm
		)

