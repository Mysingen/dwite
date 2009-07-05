import traceback
import sys

import tactile

from threading import Thread
from Queue     import Queue

from display   import Display
from tactile   import IR, TactileEvent
from menu      import Menu

class Device(Thread):
	volume  = (0,0) # don't know yet what to put here
	queue   = None  # let other threads post events here
	alive   = True  # controls the main loop
	wire    = None  # must have a wire to send actual commands to the device

	def __new__(cls, wire):
		object = super(Device, cls).__new__(cls, None, Device.run, 'Device', (),{})
		Device.__init__(object, wire)
		return object

	def __init__(self, wire):
		Thread.__init__(self)
		self.wire  = wire
		self.queue = Queue(100)

	def run(self):
		raise Excepion, 'Device subclasses must implement run()'
	
	def stop(self):
		self.alive = False

def init_acceleration_maps():
	maps    = {}
	default = [0,7,14,21,28,35,42,47,52,57,62,67,72,77,80,83,86,89,92,95,98]

	maps[IR.UP]         = default
	maps[IR.DOWN]       = default
	maps[IR.LEFT]       = default
	maps[IR.RIGHT]      = default
	maps[IR.BRIGHTNESS] = [0,10,20,30,40,50,60,70,75,80,85,90,95,100,105,110,115]

	return maps

class Classic(Device):
	display      = None
	menu         = None
	acceleration = None # hash: different messages need different acceleration
	                    # maps so keep a mapping from message codes to arrays of
		                # stress levels. mostly (only?) used for tactile events.

	def __init__(self, wire):
		Device.__init__(self, wire)
		self.display      = Display((320,32), self.wire)
		self.menu         = Menu(self.display)
		self.acceleration = init_acceleration_maps()

	def enough_stress(self, code, stress):
		if code in self.acceleration:
			# return true if the stress level is in the acceleration array for
			# the given code, or if the stress level is off the chart.
			if (stress in self.acceleration[code]
			or  stress > self.acceleration[code][-1]):
				return True
			return False
		return True # always return True for untracked codes

	def run(self):
		last_tactile = None # tuple: (msg, stress)

		while(self.alive):
			msg    = None
			stress = 0

			try:
				# regrettably, the timeout value is hand tuned...
				msg = self.queue.get(block=True, timeout=0.03)
			except Exception, e:
				# no message in the queue. tick the current menu render
				self.menu.tick()
				if last_tactile:
					msg    = last_tactile[0]
					stress = last_tactile[1] + 1
				else:
					continue
			print('stress: %s %d' % (IR.codes_debug[msg.code], stress))

			# abort handling early if the stress level isn't high enough. note
			# that the stress is always "enough" if stress is zero or the event
			# doesn't have a stress map at all.
			if not self.enough_stress(msg.code, stress):
				last_tactile = (msg, stress)
				continue
			print('ENOUGH')

			try:
				if isinstance(msg, TactileEvent):
					if msg.code == IR.RELEASE:
						# whatever button was pressed has been released
						last_tactile = None
						print('Classic RELEASE')
						continue
					
					if msg.code == IR.UP:
						self.menu.draw(self.menu.up())
					elif msg.code == IR.DOWN:
						self.menu.draw(self.menu.down())
					elif msg.code == IR.RIGHT:
						self.menu.draw(self.menu.enter())
					elif msg.code == IR.LEFT:
						self.menu.draw(self.menu.leave())
					elif msg.code == IR.BRIGHTNESS:
						self.display.next_brightness()

					last_tactile = (msg, stress)

			except Exception, e:
				traceback.print_tb(sys.exc_info()[2])
				print e
				self.alive = False
