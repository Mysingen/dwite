from datetime import datetime, timedelta

from protocol import Audg, Aude
from wire     import SlimWire
from render   import VolumeMeter

class Volume:
	wire    = None
	mute    = False
	preamp  = 0    # int 0-255
	left    = 0    # int 0-100
	right   = 0    # int 0-100
	meter   = None # VolumeMeter renderer
	timeout = None # indicates how long the meter should be kept visible
	
	def __init__(self, wire, mute, preamp, left, right, visual):
		if not type(wire) == SlimWire:
			raise Exception('Invalid Volume.wire object: %s' % str(wire))
		if not type(preamp) == int or preamp < 0 or preamp > 255:
			raise Exception('Invalid Volume.preamp value: %s' % str(preamp))
		if not type(left) == int or left < 0 or left > 100:
			raise Exception('Invalid Volume.left value: %s' % str(left))
		if not type(right) == int or right < 0 or right > 100:
			raise Exception('Invalid Volume.right value: %s' % str(right))
		self.wire   = wire
		self._mute  = mute
		self.preamp = preamp
		self.left   = left
		self.right  = right
		if visual:
			self.meter = VolumeMeter()
		self.mute(mute, mute)
		self.set_volume(left, right)
		self.timeout = datetime.now()

	@classmethod
	def dump_defaults(cls):
		return {
			'mute'  : False,
			'preamp': 255,
			'left'  : 70,
			'right' : 70,
			'visual': True
		}

	def dump_settings(self):
		return {
			'mute'  : self._mute,
			'preamp': self.preamp,
			'left'  : self.left,
			'right' : self.right,
			'visual': self.meter != None
		}

	def mute(self, analog, digital):
		aude         = Aude()
		aude.analog  = not analog  # not mute == enable
		aude.digital = not digital
		self.wire.send(aude.serialize())
		if self.meter:
			self.meter.curry(0)

	def up(self):
		self.set_volume(self.left + 1, self.right + 1)
		self.timeout = datetime.now() + timedelta(milliseconds=1000)

	def down(self):
		self.set_volume(self.left - 1, self.right - 1)
		self.timeout = datetime.now() + timedelta(milliseconds=1000)

	def set_volume(self, left, right):
		if left >= 0 and left <= 100:
			self.left = left
		if right >= 0 and right <= 100:
			self.right = right
		audg = Audg(True, self.preamp, self.left, self.right)
		self.wire.send(audg.serialize())
		if self.meter:
			self.meter.curry(self.left)

