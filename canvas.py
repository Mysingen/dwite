import sys
import struct
import socket

from datetime import datetime, timedelta

# PIL dependencies
import Image
import ImageDraw
import ImageFont

TRANSITION_NONE         = ' '
TRANSITION_SCROLL_UP    = 'u'
TRANSITION_SCROLL_DOWN  = 'd'
TRANSITION_SCROLL_LEFT  = 'l'
TRANSITION_SCROLL_RIGHT = 'r'
TRANSITION_BOUNCE_UP    = 'U'
TRANSITION_BOUNCE_DOWN  = 'D'
TRANSITION_BOUNCE_LEFT  = 'L'
TRANSITION_BOUNCE_RIGHT = 'R'

def send_grfe(s, bitmap, transition):
	cmd      = 'grfe'
	offset   = struct.pack('H', socket.htons(0))
	distance = struct.pack('B', 0)
	payload  = cmd + offset + transition + distance + bitmap
	length   = socket.htons(len(payload))
	length   = struct.pack('H', length)

	s.send(length + payload)

class Canvas:
	image    = None # private member
	drawable = None # an ImageDraw object for others to interact with
	medium   = None # we always initialize this to a "wire" medium. i.e. a socket

	# the full SqueezeBox display is divided into stripes. depending on what is
	# to be done, it should be thought of either as 320 vertical stripes of 1x32,
	# or 4 horizontal stripes of 320x8. the vertical stripes are used to put bits
	# on the wire, while the horizontal are used for device specific compositing.
	# neither is a useful concept for "artistic" compositing. for that we keep a
	# PIL drawable that some other class can render content onto.

	def __init__(self, medium):
		self.medium   = medium
		self.image    = Image.new('1', (320, 32), 0)
		self.drawable = ImageDraw.Draw(self.image)

	def clear(self):
		self.drawable.rectangle((0,0,320,32), fill=0)
	
	def redraw(self, transition):
		# SqueezeBox expects each 8 bit part of each vertical stripe to be sent
		# in big endian bit order. unfortunately, this conflicts with the natural
		# traverse order of drawables, but we can easily prepare the entire image
		# for the transmission by transposing the horizontal stripes.
		for y in [8, 16, 24, 32]:
			box = (0, y-8, 320, y)
			sub = self.image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
			self.image.paste(sub, box)
		self.image.save('blaha.png', 'PNG')

		# pack each vertical stripe into unsigned 32 bit integers
		pack = []
		data = list(self.image.getdata()) # len() == 320*32
		for i in range(320):
			stripe = 0
			for j in range(32):
				stripe = stripe | (data[j * 320 + i] << j)
			pack.append(struct.pack('L', stripe))

		bitmap = ''.join(pack) # ready for transmission
		send_grfe(self.medium, bitmap, transition)

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

	def tick(self):
		now = datetime.now()
		if now < self.timeout:
			return
		self.canvas.clear()
		self.canvas.drawable.text((0,0), self.text, font=self.font, fill=1)
		self.canvas.redraw(TRANSITION_NONE)
		self.timeout = now + timedelta(milliseconds=500)

# def render_text(string):
# 	image = Image.new('1', (320, 32), 0)
# 	draw  = ImageDraw.Draw(image)
# 	font  = ImageFont.truetype('/Library/Fonts/Arial.ttf', 27)
# 	draw.text((0,0), string, font=font, fill=1)
# 
# 	# transpose before outputting to the SqueezeBox. the full image is composed
# 	# of 320 stripes of 32 bits each, running from top to bottom. each 8-bit part
# 	# of each stripe has to be sent in reverse.
# 
# 	for y in [8, 16, 24, 32]:
# 		box = (0, y-8, 320, y)
# 		sub = image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
# 		image.paste(sub, box)
# 	image.save('blaha.png', 'PNG')
# 
# 	pack = []
# 	data = list(image.getdata()) # len() == 320*32
# 
# 	for i in range(320):
# 		# pack each stripe into an unsigned 32 bit integer.
# 		stripe = 0
# 		for j in range(32):
# 			stripe = stripe | (data[j * 320 + i] << j)
# 		pack.append(struct.pack('L', stripe))
# 	return ''.join(pack)
