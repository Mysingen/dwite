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
		raise Exception, 'Your Render (sub)class instance has no tick() method'

class TextRender(Render):
	font = None
	text = None

	def __init__(self, canvas, font_path, size):
		self.canvas = canvas
		self.font   = ImageFont.truetype(font_path, size)

	def render(self, text):
		self.text = text
		self.canvas.clear()
		self.canvas.drawable.text((0,0), self.text, font=self.font, fill=1)

	def tick(self):
		now = datetime.now()
		if now < self.timeout:
			return
		self.canvas.clear()
		self.canvas.drawable.text((0,0), self.text, font=self.font, fill=1)
		self.canvas.redraw(TRANSITION_NONE)
		self.timeout = now + timedelta(milliseconds=500)

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
