# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import os
from datetime import datetime, timedelta

# PIL dependencies
import Image, ImageDraw, ImageFont

class Render:
	canvas  = None
	timeout = datetime.now()

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
		if self.timeout < test:
			self.timeout = test

class Window:
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

	def __new__(cls, font_path, size, position):
		global singleton
		key = (font_path, size, position)
		if key in singleton:
			object = singleton[key]
		else:
			object = Render.__new__(cls)
			TextRender.__init__(object, font_path, size, position)
			singleton[key] = object
		return object

	def __init__(self, font_path, size, position):
		self.font     = ImageFont.truetype(font_path, size)
		self.image    = None
		self.window   = None
		self.timeout  = None
		self.position = position

	def curry(self, text):
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
			self.window = self.make_window(canvas.size)
			self.draw([self.position])
			canvas.paste(self.image)
			#print('first')
			if self.image:
				self.timeout = datetime.now() + timedelta(milliseconds=1000)
			else:
				self.timeout = datetime.now() + timedelta(days=1)
			return True

		if not self.window:
			#print('never')
			canvas.paste(self.image)
			return False # no need to redraw. ever.

		now = datetime.now()
		if now < self.timeout:
			#print('later')
			canvas.paste(self.image)
			return False

		#print('now')
		positions = self.window.advance(5)
		positions = [(p, self.position[1]) for p in positions]
		self.image = Image.new('1', canvas.size, 0)
		self.draw(positions)
		canvas.paste(self.image)
		self.timeout = now + timedelta(milliseconds=100)
		return True

class ProgressRender(Render):
	progress = 0.0 # float: 0.0-1.0
	x_size   = 100
	y_size   = 2
	position = (200, 0)
	image    = None

	def __new__(cls, progress=0):
		global singleton
		key = cls
		if key in singleton:
			object = singleton[key]
		else:
			object = Render.__new__(cls)
			singleton[key] = object
		ProgressRender.__init__(object, progress)
		return object

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
	def __init__(self, label):
		home = os.getenv('DWITE_HOME')
		self.base = TextRender(
			'%s/fonts/LiberationMono-Bold.ttf' % home, 35, (2, 0)
		)
		self.base.curry(label)
		self.overlay = ProgressRender()

	def curry(self, progress):
		self.overlay.curry(progress)

class SearchRender(Render):
	query = None
	term  = None

	def __init__(self):
		home = os.getenv('DWITE_HOME')
		self.query = TextRender(
			'%s/fonts/LiberationMono-Regular.ttf' % home, 10, (2, 0)
		)
		self.term = TextRender(
			'%s/fonts/LiberationMono-Regular.ttf' % home, 20, (2, 10)
		)

	# TODO: would be nice if ticking of self.query wasn't interrupted by
	# key presses to form the next term. only applicable when the query
	# becomes long enough that it has to be scrolled.
	def tick(self, canvas):
		t1 = self.query.tick(canvas)
		t2 = self.term.tick(canvas)
		return (t1 or t2)

	def curry(self, term_text, query_text):
		self.query.curry(query_text)
		self.term.curry(term_text)

