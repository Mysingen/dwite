import sys
import struct

from datetime import datetime, timedelta

# PIL dependencies
import Image
import ImageDraw
import ImageFont

class Canvas:
	bitmap   = ''   # Suitable for output to SqueezeBox with the GRFE command
	image    = None # private member
	drawable = None # an ImageDraw object for others to interact with

	# the full SqueezeBox display is divided into stripes. depending on what is
	# to be done, it should be thought of either as 320 vertical stripes of 1x32,
	# or 4 horizontal stripes of 320x8. the vertical stripes are used to put bits
	# on the wire, while the horizontal are used for device specific compositing.
	# neither is a useful concept for "artistic" compositing. for that we keep a
	# PIL drawable that some other class can render content onto.

	def __init__(self):
		self.image    = Image.new('1', (320, 32), 0)
		self.drawable = ImageDraw.Draw(self.image)

	def __str__(self):
		return self.bitmap

	def clear(self):
		self.drawable.rectangle((0,0,320,32), fill=0)
	
	def redraw(self):
		# SqueezeBox expects each 8 bit part of each vertical stripe to be sent
		# in big endian bit order. unfortunately, this conflicts with the natural
		# traverse order of drawables, but we can easily prepare the entire image
		# for the transmission by transposing the horizontal stripes.
		for y in [8, 16, 24, 32]:
			box = (0, y-8, 320, y)
			sub = self.image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
			self.image.paste(sub, box)

		# pack each vertical stripe into unsigned 32 bit integers
		pack = []
		data = list(self.image.getdata()) # len() == 320*32
		for i in range(320):
			stripe = 0
			for j in range(32):
				stripe = stripe | (data[j * 320 + i] << j)
			pack.append(struct.pack('L', stripe))

		self.bitmap = ''.join(pack) # ready for transmission

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

class TextRender(Render):
	canvas  = None
	font    = None
	text    = None
	window  = None
	timeout = None

	def __init__(self, canvas, font_path, size):
		self.canvas = canvas
		self.font   = ImageFont.truetype(font_path, size)

	def render(self, text, position):
		self.text = text
		(x,y) = self.canvas.drawable.textsize(self.text, font=self.font)
		if x > 318:
			if position < 0:
				position = 320 - x
			self.window  = Window(320, 10, x, position)
			self.timeout = datetime.now() + timedelta(milliseconds=1000)
		else:
			self.window  = None
			self.timeout = None
		self.canvas.clear()
		self.canvas.drawable.text((position,0), self.text, font=self.font, fill=1)

	def tick(self):
		if not self.window:
			return False
		now = datetime.now()
		if now < self.timeout:
			return False
		(x, xx) = self.window.advance(5)
		self.canvas.clear()
		self.canvas.drawable.text((x,0), self.text, font=self.font, fill=1)
		if xx >= 0:
			self.canvas.drawable.text((xx,0), self.text, font=self.font, fill=1)
		self.timeout = now + timedelta(milliseconds=100)
		return True

class Display:
	TRANSITION_NONE         = ' '
	TRANSITION_SCROLL_UP    = 'd'
	TRANSITION_SCROLL_DOWN  = 'u'
	TRANSITION_SCROLL_LEFT  = 'r'
	TRANSITION_SCROLL_RIGHT = 'l'
	TRANSITION_BOUNCE_UP    = 'U'
	TRANSITION_BOUNCE_DOWN  = 'D'
	TRANSITION_BOUNCE_LEFT  = 'R'
	TRANSITION_BOUNCE_RIGHT = 'L'
