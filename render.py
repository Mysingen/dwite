# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

from datetime import datetime, timedelta

# PIL dependencies
import ImageFont

class Render:
	canvas  = None
	timeout = datetime.now()

	# Render objects keep track of their internal frame rate by setting a timeout
	# (in absolute wall clock time) at which the next frame should be drawn. it
	# should expect that a user of the object calls its tick() method regularly
	# to drive this.

	# subclasses must implement the curry() method
	def curry(self):
		raise Exception, 'Your Render instance has no curry() method'

	# subclasses must implement the tick() method
	def tick(self):
		raise Exception, 'Your Render instance has no tick() method'

class Window:
	size    = 0
	slack   = 0 # the space to keep unpainted when the window contents wrap around
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
			return (self.current, self.current + self.content + self.slack)
		return (self.current, - 1)

	def advance(self, amount):
		prospect = (self.current - amount) + self.content + self.slack
		if prospect <= 0:
			self.current = prospect
		else:
			self.current = self.current - amount
		return self.get()

singleton = {}

class TextRender(Render):
	font    = None
	text    = None
	window  = None
	timeout = None

	def __new__(cls, font_path, size):
		global singleton
		key = (font_path, size)
		if key in singleton:
			object = singleton[key]
		else:
			object = Render.__new__(cls)
			TextRender.__init__(object, font_path, size)
			singleton[key] = object
		return object

	def __init__(self, font_path, size):
		self.font = ImageFont.truetype(font_path, size)

	def curry(self, text, position):
		self.text     = text
		self.position = position

	def draw(self, canvas):
		(x,y) = canvas.drawable.textsize(self.text, font=self.font)
		if x > canvas.size[0] - self.position:
			# will render outside canvas right side. create a sliding window
			# and let it show its starting position for a full second
			self.window  = Window(canvas.size[0], 10, x, self.position)
			self.timeout = datetime.now() + timedelta(milliseconds=1000)
		else:
			self.window  = None
			self.timeout = None
		canvas.drawable.text((self.position,0),self.text, font=self.font,fill=1)
		return True

	def tick(self, canvas):
		now = datetime.now()
		if (not self.window) or (now < self.timeout):
			x  = self.position
			xx = -1
		else:
			(x, xx) = self.window.advance(5)
			self.timeout = now + timedelta(milliseconds=100)
		canvas.drawable.text((x,0), self.text, font=self.font, fill=1)
		if xx >= 0:
			canvas.drawable.text((xx,0), self.text, font=self.font, fill=1)
		return True

class ProgressRender(Render):
	progress = 0 # float: 0.0-1.0
	x_size   = 100
	y_size   = 2
	position = (200, 0)

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

	def __init__(self, progress=0):
		self.progress = progress
		print('progress = %f' % progress)

	def draw(self, canvas):
		# tl = top left, lr = lower right
		outer_tl = self.position
		outer_lr = (self.position[0] + self.x_size + 4,
		            self.position[1] + self.y_size + 4)
		inner_tl = (self.position[0] + 2, self.position[1] + 2)
		inner_lr = (self.position[0] + 2 + int(self.x_size * self.progress),
		            self.position[1] + 2 +  self.y_size)

		print('%s %s' % (str([outer_tl, outer_lr]), str([inner_tl, inner_lr])))
		
		canvas.drawable.rectangle([outer_tl, outer_lr], outline=1, fill=0)
		canvas.drawable.rectangle([inner_tl, inner_lr], outline=1, fill=1)
		return True

	def tick(self, canvas):
		now = datetime.now()
		if now < self.timeout:
			return False
		self.draw(canvas)
		self.timeout = now + timedelta(milliseconds=100)
		return True
