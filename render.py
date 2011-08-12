# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os

from datetime import datetime, timedelta

# PIL dependencies
import Image, ImageDraw, ImageFont

import fonts

class Render(object):
	canvas  = None
	timeout = datetime.now()
	mode    = None

	# Render objects keep track of their internal frame rate by setting a
	# timeout (in absolute wall clock time) at which the next frame should
	# be drawn. it should expect that a user of the object calls its tick()
	# method regularly to drive this.

	# subclasses must implement the curry() method
	def curry(self):
		raise Exception, 'Your Render instance has no curry() method'

	# subclasses must implement the tick() method
	def tick(self, canvas):
		raise Exception, 'Your Render instance has no tick() method'

	def min_timeout(self, msecs):
		now   = datetime.now()
		delta = timedelta(milliseconds=msecs)
		test  = now + delta
		if not self.timeout or self.timeout < test:
			self.timeout = test

	# subclasses that have different display should look at self.mode
	def	next_mode(self):
		pass

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
	image    = None
	font     = None
	text     = None
	window   = None
	timeout  = None
	position = (0, 0)
	_scroll  = True

	@property
	def scroll(self):
		return self._scroll

	@scroll.setter
	def scroll(self, value):
		if value != self._scroll:
			self.image = None
		self._scroll = value

	def __new__(cls, font_path, size, position, scroll=True):
		global singleton
		key = (font_path, size, position)
		if key in singleton:
			obj = singleton[key]
		else:
			obj = Render.__new__(cls)
			TextRender.__init__(obj, font_path, size, position)
			singleton[key] = obj
		return obj

	def __init__(self, font_path, size, position, scroll=True):
		self.font     = ImageFont.truetype(font_path, size)
		self.image    = None
		self.window   = None
		self.timeout  = None
		self.position = position
		self._scroll  = scroll

	def curry(self, text):
		assert type(text) == unicode
#		if len(text) < 1:
#			raise Exception('len(TextRender.text = %s) < 1' % text)
		self.text  = text
		self.image = None

	def draw(self, positions):
		draw = ImageDraw.Draw(self.image)
		for p in positions:
			draw.text(p, self.text, font=self.font, fill=1)

	def make_window(self, size):
		draw  = ImageDraw.Draw(self.image)
		(x,y) = draw.textsize(self.text, font=self.font)
		if x > size[0] - self.position[0]:
			# would render outside image's right side. create a sliding window
			return Window(size[0], 10, x, self.position[0])
		return None

	def tick(self, canvas):
		if not self.image: # never called this render's tick() before
			self.image = Image.new('1', canvas.size, 0)
			if self._scroll:
				self.window = self.make_window(canvas.size)
			else:
				self.window = None
			self.draw([self.position])
			canvas.paste(self.image)
			#print('first')
			if self.image:
				self.timeout = datetime.now() + timedelta(milliseconds=1000)
			else:
				self.timeout = datetime.now() + timedelta(years=1)
			return True

		now = datetime.now()
		if self.image and self.timeout and now < self.timeout:
			#print('later')
			canvas.paste(self.image)
			return False

		#print('now')
		self.image = Image.new('1', canvas.size, 0)
		if self.window:
			positions = self.window.advance(5)
			positions = [(p, self.position[1]) for p in positions]
			self.draw(positions)
		else:
			self.draw([self.position])
		canvas.paste(self.image)
		self.timeout = now + timedelta(milliseconds=100)
		return True

class HighlightTextRender(TextRender):
	bold_render    = None
	regular_render = None
	bold_len       = 0
	
	def __new__(cls, font_name, size, position):
		global singleton
		key = (cls, font_name, size)
		if key in singleton:
			obj = singleton[key]
		else:
			obj = Render.__new__(cls)
			HighlightTextRender.__init__(obj, font_name, size, position)
			singleton[obj] = obj
		return obj
	
	def __init__(self, font_name, size, position):
		bold_path    = fonts.get_path('%s-Bold' % font_name)
		regular_path = fonts.get_path('%s-Regular' % font_name)
		TextRender.__init__(self, bold_path, size, position)
		self.bold_font    = self.font
		self.regular_font = ImageFont.truetype(regular_path, size)

	def draw(self, positions):
		draw = ImageDraw.Draw(self.image)
		for p in positions:
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
		self.text     = text
		self.bold_len = bold_len

class RENDER_MODE:
	LABEL  = 1
	PRETTY = 2

class ItemRender(TextRender):
	mode = RENDER_MODE.LABEL

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
	
	def curry(self, level):
		if type(level) != int or level < 0 or level > 100:
			raise Exception('Invalid VolumeMeter.level = %s' % str(level))
		self.level = level
	
	def draw(self):
		# draw one vertical bar per level. space them by on pixel from left
		# to right, starting at position[0].
		draw = ImageDraw.Draw(self.image)
		for i in range(0, self.level):
			draw.line(
				[(self.position[0] + i * 2, self.position[1]),
				 (self.position[0] + i * 2, self.position[1] + self.size[1])],
				fill=1
			)
	
	def tick(self, canvas):
		if not self.image: # never called this render's tick() before
			self.image = Image.new('1', canvas.size, 0)
			self.draw()
			canvas.paste(self.image)
			return True
		
		self.image = Image.new('1', canvas.size, 0)
		self.draw()
		canvas.paste(self.image)
		return True

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

	def curry(self, progress):
		self.progress = progress

	def draw(self):
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

	def tick(self, canvas):
		if not self.image: # never called this render's tick() before
			self.image = Image.new('1', canvas.size, 0)
			self.draw()
			canvas.paste(self.image)
			return True

		now = datetime.now()
		if now < self.timeout:
			canvas.paste(self.image)
			return False

		self.image = Image.new('1', canvas.size, 0)
		self.draw()
		canvas.paste(self.image)
		self.timeout = now + timedelta(milliseconds=500)
		return True

class OverlayRender(Render):
	base    = None
	overlay = None
	
	def __init__(self, base, overlay):
		self.base    = base
		self.overlay = overlay
	
	def tick(self, canvas):
		if datetime.now() < self.timeout:
			return False
		t1 = self.base.tick(canvas)
		t2 = self.overlay.tick(canvas)
		return (t1 or t2)

class NowPlayingRender(OverlayRender):
	def __init__(self):
		self.base = ItemRender(fonts.get_path('LiberationMono-Bold'), 35, (2,0))
		self.base.mode = RENDER_MODE.PRETTY
		self.overlay = ProgressRender()

	def curry(self, progress, item):
		if item:
			self.base.curry(item)
		self.overlay.curry(progress)

	def next_mode(self):
		self.base.next_mode()

class SearchRender(Render):
	query = None
	term  = None
	
	@property
	def scroll(self):
		return self.term.scroll
	
	@scroll.setter
	def scroll(self, value):
		assert type(value) == bool
		self.term.scroll = value

	def __init__(self):
		self.query = TextRender(
			fonts.get_path('LiberationMono-Regular'), 10, (2, 0)
		)
		self.term = HighlightTextRender('LiberationMono', 20, (2, 10))

	# TODO: would be nice if ticking of self.query wasn't interrupted by
	# key presses to form the next term. only applicable when the query
	# becomes long enough that it has to be scrolled.
	def tick(self, canvas):
		t1 = self.query.tick(canvas)
		t2 = self.term.tick(canvas)
		return (t1 or t2)

	def curry(self, term_text, query_text, term_len=0):
		self.query.curry(query_text)
		self.term.curry(term_text, term_len)

