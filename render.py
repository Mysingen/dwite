# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
import sys
import traceback

from datetime import datetime, timedelta

# PIL dependencies
import Image, ImageDraw, ImageFont

import fonts

class Render(object):
	timeout = None
	mode    = None
	image   = None
	timeout = None

	def __init__(self):
		self.timeout = datetime.now()

	# Render objects keep track of their internal frame rate by setting a
	# timeout (in absolute wall clock time) at which the next frame should
	# be drawn. it should expect that a user of the object calls its tick()
	# method regularly to drive this.

	def dump(self):
		raise Exception('Render sub-classes must implement dump()')

	def draw(self):
		raise Exception('Render sub-classes must implement draw()')

	# subclasses must implement the curry() method
	def curry(self):
		pass

	# subclasses must implement the tick() method
	def tick(self, canvas, force=False):
		if self.expired(force):
			self.image = Image.new('1', canvas.size, 0)
			self.draw()
			self.timeout = datetime.now() + timedelta(milliseconds=100)
			return True
		return False

	def min_timeout(self, msecs):
		test = datetime.now() + timedelta(milliseconds=msecs)
		if test > self.timeout:
			self.timeout = test

	# subclasses that have different display should look at self.mode
	def	next_mode(self):
		pass

	def expired(self, force):
		if force:
#			sys.stdout.write('X')
#			sys.stdout.flush()
			return True
		if not self.timeout:
#			sys.stdout.write('Q')
#			sys.stdout.flush()
			return True
		if self.timeout < datetime.now():
#			sys.stdout.write('v')
#			sys.stdout.flush()
			return True
#		sys.stdout.write('^')
#		sys.stdout.flush()
		return False

class Window(object):
	size    = 0
	slack   = 0 # the space to keep unpainted when the window contents wrap
	start   = 0
	current = 0
	content = 0 # set by the user

	def __init__(self, size, slack, content, start):
		self.size    = size
		self.slack   = slack
		self.start   = start
		self.content = content
		self.current = self.start

	def get(self):
		if self.current + self.content + self.slack < self.size:
			return [self.current, self.current + self.content + self.slack]
		return [self.current]

	def advance(self, amount):
		prospect = (self.current - amount) + self.content + self.slack
		if prospect <= 0:
			self.current = prospect
		else:
			self.current = self.current - amount
		return self.get()

singleton = {}

class TextRender(Render):
	font     = None
	text     = None
	window   = None
	timeout  = None
	position = (0, 0)
	scroll   = True
	positions = None

	def __new__(cls, font_path, size, position, scroll=True):
		global singleton
		key = (font_path, size, position, scroll)
		if key in singleton:
			obj = singleton[key]
		else:
			obj = Render.__new__(cls)
			TextRender.__init__(obj, font_path, size, position, scroll)
			singleton[key] = obj
		return obj

	def __init__(self, font_path, size, position, scroll=True):
		self.font     = ImageFont.truetype(font_path, size)
		self.position = position
		self.scroll   = scroll

	def curry(self, text):
		assert type(text) == unicode
		self.text    = text
		self.window  = False
		Render.curry(self)

	def dump(self):
		return {
			'type': type(self),
			'text': self.text,
			'id'  : id(self)
		}

	def draw(self):
		assert self.image
		draw = ImageDraw.Draw(self.image)
		for p in self.positions:
			draw.text(p, self.text, font=self.font, fill=1)

	def make_window(self, size):
		assert self.image
		draw  = ImageDraw.Draw(self.image)
		(x,y) = draw.textsize(self.text, font=self.font)
		if x > size[0] - self.position[0]:
			# would render outside image's right side. create a sliding window
			return Window(size[0], 10, x, self.position[0])
		return None

	def tick(self, canvas, force=False):
		if not self.expired(force):
			return False
		
		self.timeout = datetime.now() + timedelta(milliseconds=100)
		self.image = Image.new('1', canvas.size, 0)
		if self.scroll:
			if not self.window:
				self.window  = self.make_window(canvas.size)
				self.timeout = datetime.now() + timedelta(milliseconds=1000)
				self.positions = [self.position]
			else:
				positions = self.window.advance(5)
				self.positions = [(p, self.position[1]) for p in positions]
		else:
			self.positions = [self.position]
		self.draw()
		return True

class HighlightTextRender(TextRender):
	regular_font = None
	bold_font    = None
	bold_len     = 0
	
	def __new__(cls, font_name, size, position, scroll):
		global singleton
		key = (cls, font_name, size)
		if key in singleton:
			obj = singleton[key]
		else:
			obj = Render.__new__(cls)
			HighlightTextRender.__init__(obj, font_name, size, position, scroll)
			singleton[obj] = obj
		return obj
	
	def __init__(self, font_name, size, position, scroll):
		bold_path    = fonts.get_path('%s-Bold' % font_name)
		regular_path = fonts.get_path('%s-Regular' % font_name)
		TextRender.__init__(self, bold_path, size, position, scroll)
		self.bold_font    = self.font
		self.regular_font = ImageFont.truetype(regular_path, size)

	def dump(self):
		return {
			'type': type(self),
			'text': self.text,
			'bold': self.bold_len,
			'id'  : id(self)
		}

	def draw(self):
		assert self.image
		draw = ImageDraw.Draw(self.image)
		for p in self.positions:
			# first draw the bold text. then check how much space that took
			# on the X axis...
			b_text = self.text[:self.bold_len].upper()
			draw.text(p, b_text, font=self.bold_font, fill=1)
			(w, h) = draw.textsize(b_text, font=self.bold_font)
			# ...and add that to an infered starting position for regular text
			p2 = (p[0]+w, p[1])
			r_text = self.text[self.bold_len:]
			draw.text(p2, r_text, font=self.regular_font, fill=1)
	
	def curry(self, text, bold_len=0):
		assert type(text) == unicode
		assert len(text)  >= bold_len
		self.bold_len = bold_len
		TextRender.curry(self, text)

class RENDER_MODE:
	LABEL  = 1
	PRETTY = 2

class ItemRender(TextRender):
	mode = RENDER_MODE.LABEL

	def dump(self):
		return {
			'type': type(self),
			'text': self.text,
			'mode': self.mode,
			'id'  : id(self)
		}

	def curry(self, item):
		if self.mode == RENDER_MODE.LABEL:
			TextRender.curry(self, item.label)
		if self.mode == RENDER_MODE.PRETTY:
			TextRender.curry(self, item.get_pretty())

	def next_mode(self):
		if self.mode == RENDER_MODE.LABEL:
			self.mode = RENDER_MODE.PRETTY
		else:
			self.mode = RENDER_MODE.LABEL

class VolumeMeter(Render):
	level    = 0 # integer 0-100
	size     = (200, 30)
	position = (59, 1)
	image    = None
	
	def __new__(cls):
		global singleton
		if cls in singleton:
			obj = singleton[cls]
		else:
			obj = Render.__new__(cls)
			singleton[cls] = obj
		VolumeMeter.__init__(obj)
		return obj
	
	def __init__(self):
		pass

	def dump(self):
		return {
			'type' : type(self),
			'level': self.level,
			'id'   : id(self)
		}

	def curry(self, level):
		assert type(level) == int and level >= 0 and level <= 100
		self.level = level
		Render.curry(self)
	
	def draw(self):
		assert self.image
		draw = ImageDraw.Draw(self.image)
		# draw one vertical bar per level. space them by on pixel from left
		# to right, starting at position[0].
		for i in range(0, self.level):
			draw.line(
				[(self.position[0] + i * 2, self.position[1]),
				 (self.position[0] + i * 2, self.position[1] + self.size[1])],
				fill=1
			)

class ProgressRender(Render):
	progress = 0.0 # float: 0.0-1.0
	x_size   = 100
	y_size   = 2
	position = (200, 0)
	image    = None

	# __new__() should not be implemented to use singletons. If there is only
	# one, then there is a race condition between seeking and playback. Regular
	# playback progress updates will overwrite the progress indicated by the
	# seeker. The visible effect is that the progress bar is not updated
	# correctly while the user is pressing REW or FWD.

	def __init__(self, progress=0.0):
		self.progress = progress

	def dump(self):
		return {
			'type'    : type(self),
			'progress': self.progress,
			'id'      : id(self)
		}

	def curry(self, progress):
		Render.curry(self)
		self.progress = progress

	def draw(self):
		assert self.image
		# tl = top left, lr = lower right
		outer_tl = self.position
		outer_lr = (self.position[0] + self.x_size + 4,
		            self.position[1] + self.y_size + 4)
		inner_tl = (self.position[0] + 2, self.position[1] + 2)
		inner_lr = (self.position[0] + 2 + int(self.x_size * self.progress),
		            self.position[1] + 2 +  self.y_size)

		draw = ImageDraw.Draw(self.image)
		draw.rectangle([outer_tl, outer_lr], outline=1, fill=0)
		draw.rectangle([inner_tl, inner_lr], outline=1, fill=1)

class OverlayRender(Render):
	base    = None
	overlay = None

	def __init__(self, base, overlay):
		Render.__init__(self)
		self.base    = base
		self.overlay = overlay

	def dump(self):
		return {
			'type'   : type(self),
			'base'   : self.base.dump(),
			'overlay': self.overlay.dump(),
			'id'     : id(self)
		}

	def draw(self):
		self.image = Image.composite(
			self.base.image, self.overlay.image, self.base.image
		)

	def tick(self, canvas, force=False):
		t1 = self.base.tick(canvas, force)
		t2 = self.overlay.tick(canvas, force)
		self.draw()
		return t1 or t2

	def min_timeout(self, msecs):
		self.base.min_timeout(msecs)
		self.overlay.min_timeout(msecs)

class NowPlayingRender(OverlayRender):
	def __init__(self):
		item = ItemRender(fonts.get_path('LiberationMono-Bold'), 35, (2,0))
		item.mode = RENDER_MODE.PRETTY
		progress = ProgressRender()
		OverlayRender.__init__(self, item, progress)

	def curry(self, progress, item):
		if item:
			self.base.curry(item)
		self.overlay.curry(progress)

	def next_mode(self):
		self.base.next_mode()

class SearchRender(OverlayRender):
	def __init__(self, scroll):
		query = TextRender(
			fonts.get_path('LiberationMono-Regular'), 10, (2, 0), True
		)
		term = HighlightTextRender('LiberationMono', 20, (2, 10), scroll)
		OverlayRender.__init__(self, query, term)

	def curry(self, term_text, query_text, term_len=0):
		self.base.curry(query_text)
		self.overlay.curry(term_text, term_len)

