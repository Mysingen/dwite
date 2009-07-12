# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

from canvas   import Canvas
from protocol import Grfe, Grfb, VisuNone, VisuMeter

# no intantiation of BRIGHTNESS is needed since it only carries constants
# that share a name space.
class BRIGHTNESS:
	# syntactic sugar for the valid indeces into the brightness map. the map
	# holds the actual hardware codes that a Display instance knows how to
	# treat.
	OFF   = 0
	ONE   = 1
	TWO   = 2
	THREE = 3
	FULL  = 4
	map   = [65535, 0, 1, 3, 4]

# no instantiation of TRANSITION is needed since it only carries contstants
# that share a name space.
class TRANSITION:
	NONE         = 'c'
	SCROLL_UP    = 'd'
	SCROLL_DOWN  = 'u'
	SCROLL_LEFT  = 'r'
	SCROLL_RIGHT = 'l'
	BOUNCE_UP    = 'U'
	BOUNCE_DOWN  = 'D'
	BOUNCE_LEFT  = 'R'
	BOUNCE_RIGHT = 'L'

all_visualizers = [
	VisuNone(),
	VisuMeter(),
	VisuMeter(0,159, 161,159)
]

class Display:
	wire        = None
	brightness  = BRIGHTNESS.FULL
	canvas      = None
	visualizers = iter(all_visualizers)
	
	def __init__(self, size, wire):
		self.wire   = wire
		self.canvas = Canvas(size)

	def set_brightness(self, brightness):
		if brightness < BRIGHTNESS.OFF or brightness > BRIGHTNESS.FULL:
			raise Exception, 'Unknown brightness code %d' % brightness
		self.brightness = brightness
		grfb = Grfb()
		grfb.brightness = BRIGHTNESS.map[self.brightness]
		self.wire.send(grfb.serialize())
	
	def next_brightness(self):
		if self.brightness - 1 < BRIGHTNESS.OFF:
			self.set_brightness(BRIGHTNESS.FULL)
		else:
			self.set_brightness(self.brightness - 1)

	def next_visualizer(self):
		try:
			visu = self.visualizers.next()
			self.wire.send(visu.serialize())
		except:
			self.visualizers = iter(all_visualizers)
			self.next_visualizer()

	def show(self, transition):
		self.canvas.prepare_transmission()
		grfe = Grfe()
		grfe.transition = transition
		grfe.bitmap     = self.canvas.bitmap
		self.wire.send(grfe.serialize())
