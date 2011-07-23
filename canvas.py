# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import struct

# PIL dependencies
import Image
import ImageDraw

class Canvas:
	bitmap   = ''    # Suitable for output to SqueezeBox with 'grfe' command
	image    = None  # private member
	size     = None  # pixel size of the drawable. tuple (x,y)

	# the full SqueezeBox display is divided into stripes. depending on what
	# is to be done, it should be thought of either as 320 vertical stripes
	# of 1x32, or 4 horizontal stripes of 320x8. the vertical stripes are
	# used to put bits on the wire, while the horizontal are used for device
	# specific compositing. neither are useful concepts for more "artistic"
	# compositing. for that we keep a PIL drawable that some other class can
	# render content onto.

	def __init__(self, size):
		self.size = size
		self.clear()

	def clear(self):
		self.image = Image.new('1', self.size, 0)
	
	def paste(self, image):
		assert image != None
		self.image = Image.composite(self.image, image, self.image)
	
	def prepare_transmission(self):
		# SqueezeBox expects each 8 bit part of each vertical stripe to be
		# sent in big endian bit order. unfortunately, this conflicts with
		# the natural traverse order of drawables, but we can easily prepare
		# the entire image for the transmission by transposing the horizontal
		# stripes.
		for y in [8, 16, 24, 32]:
			box = (0, y-8, self.size[0], y)
			sub = self.image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
			self.image.paste(sub, box)

		# pack each vertical stripe into unsigned 32 bit integers
		pack = []
		data = list(self.image.getdata()) # len() == x*y
		for i in range(self.size[0]):
			stripe = 0
			for j in range(self.size[1]):
				stripe = stripe | (data[j * self.size[0] + i] << j)
			pack.append(struct.pack('<L', stripe))

		self.bitmap = ''.join(pack) # ready for transmission
