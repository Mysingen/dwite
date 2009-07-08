import traceback
import sys

from threading import Thread
from Queue     import Queue

from display   import Display
from tactile   import IR, TactileEvent
from menu      import Menu
from player    import Player

class Device(Thread):
	volume  = (0,0) # don't know yet what to put here
	queue   = None  # let other threads post events here
	alive   = True  # controls the main loop
	wire    = None  # must have a wire to send actual commands to the device
	menu    = None  # all devices must have a menu system
	guid    = None  # string that uniqely identifies the device. usualy MAC addr.
	player  = None

	def __new__(cls, wire, queue, guid):
		object = super(Device, cls).__new__(
			cls, None, Device.run, 'Device', (),{})
		Device.__init__(object, wire, queue, guid)
		return object

	def __init__(self, wire, queue, guid):
		Thread.__init__(self)
		self.wire  = wire
		self.queue = queue
		self.guid  = guid
		self.menu  = Menu()

	def run(self):
		raise Excepion, 'Device subclasses must implement run()'
	
	def stop(self):
		self.alive = False

def init_acceleration_maps():
	maps    = {}
	default = [0,7,14,21,28,35,42,47,52,57,62,67,72,77,80,83,86,89,92,95,98]

	maps[IR.UP]          = default
	maps[IR.DOWN]        = default
	maps[IR.LEFT]        = default
	maps[IR.RIGHT]       = default
	maps[IR.BRIGHTNESS]  = [0,10,20,30,40,50,60,70,75,80,85,90,95,100,105,110,115]
	maps[IR.VOLUME_UP]   = default
	maps[IR.VOLUME_DOWN] = default

	return maps

class Classic(Device):
	display      = None
	acceleration = None # dict: different messages need different acceleration
	                    # maps so keep a mapping from message codes to arrays of
		                # stress levels. mostly (only?) used for tactile events.

	def __new__(cls, wire, queue, guid):
		object = super(Classic, cls).__new__(cls, wire, queue, guid)
		Classic.__init__(object, wire, queue, guid)
		return object

	def __init__(self, wire, queue, guid):
		self.display      = Display((320,32), self.wire)
		self.acceleration = init_acceleration_maps()

		self.menu.set_display(self.display)

	def enough_stress(self, code, stress):
		if stress == 0:
			return True # special case to catch all untracked codes
		if code in self.acceleration:
			# return true if the stress level is in the acceleration array for
			# the given code, or if the stress level is off the chart.
			if (stress in self.acceleration[code]
			or  stress > self.acceleration[code][-1]):
				return True
		return False

	def run(self):
		# Python limit: the player cannot be created in __init__() because
		# the threading goes bananas. player contains more threads and threads
		# cannot be created "inside" the creation procedures of other threads.
		self.player  = Player(self.wire, self.guid)
		last_tactile = None # tuple: (msg, stress)

		while(self.alive):
			msg    = None
			stress = 0

			try:
				# waking up 50 times per second costs less than 1% CPU of a
				# single core in an Intel Core2 Duo system, so lets do that
				# to get good resolution in all ticking activities.
				msg = self.queue.get(block=True, timeout=0.02)
			except Exception, e:
				# no message in the queue. tick the current menu render
				#if last_tactile:
				#	msg    = last_tactile[0]
				#	stress = last_tactile[1] + 1
				#else:
				#	continue
				pass

			self.menu.tick()

			if not msg:
				continue

			# abort handling early if the stress level isn't high enough. note
			# that the stress is always "enough" if stress is zero or the event
			# doesn't have a stress map at all.
			if not self.enough_stress(msg.code, stress):
				last_tactile = (msg, stress)
				continue

			try:
				if isinstance(msg, TactileEvent):
					if msg.code == IR.RELEASE:
						# whatever button was pressed has been released
						last_tactile = None
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
					elif msg.code == IR.PLAY:
						self.menu.draw(self.menu.play(self.player))
					elif msg.code == IR.VOLUME_UP:
						self.player.volume_up()
					elif msg.code == IR.VOLUME_DOWN:
						self.player.volume_down()
					elif msg.code == IR.POWER or msg.code == IR.HARD_POWER:
						self.alive = False
					else:
						raise Exception, ('Unhandled code %s'
						                  % IR.codes_debug[msg.code])

					last_tactile = (msg, stress)

			except:
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]
				self.alive = False

		self.player.close()
		print('device is Dead')
