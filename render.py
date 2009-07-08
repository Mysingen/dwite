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
			object = super(TextRender, cls.__new__(cls))
			TextRender.__init__(object, font_path, size)
			singleton[key] = object
		return object

	def __init__(self, font_path, size):
		self.font = ImageFont.truetype(font_path, size)

	def draw(self, canvas, text, position):
		self.text = text
		(x,y) = canvas.drawable.textsize(self.text, font=self.font)
		if x > canvas.size[0] - 2:
			if position < 0:
				position = canvas.size[0] - x
			self.window  = Window(canvas.size[0], 10, x, position)
			self.timeout = datetime.now() + timedelta(milliseconds=1000)
		else:
			self.window  = None
			self.timeout = None
		canvas.clear()
		canvas.drawable.text((position,0), self.text, font=self.font, fill=1)
		return True

	def tick(self, canvas):
		if not self.window:
			return False
		now = datetime.now()
		if now < self.timeout:
			return False
		(x, xx) = self.window.advance(5)
		canvas.clear()
		canvas.drawable.text((x,0), self.text, font=self.font, fill=1)
		if xx >= 0:
			canvas.drawable.text((xx,0), self.text, font=self.font, fill=1)
		self.timeout = now + timedelta(milliseconds=100)
		return True
