# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys

from threading import Thread
from Queue     import Queue

from protocol  import Helo, Tactile, Stat
from display   import Display
from tactile   import IR
from menu      import Menu
from player    import Player
from render    import ProgressRender

class Device(Thread):
	queue   = None  # let other threads post events here
	alive   = True  # controls the main loop
	wire    = None  # must have a wire to send actual commands to the device
	menu    = None  # all devices must have a menu system
	guid    = None  # string. uniqely identifies the device. usualy MAC addr.
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
	default = [0,3,6,9,12,15,18,21,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52]

	maps[IR.UP]          = default
	maps[IR.DOWN]        = default
	maps[IR.LEFT]        = default
	maps[IR.RIGHT]       = default
	maps[IR.BRIGHTNESS]  = default
	maps[IR.VOLUME_UP]   = default
	maps[IR.VOLUME_DOWN] = default
	maps[IR.FORWARD]     = [0]
	maps[IR.REWIND]      = [0]

	return maps

class Classic(Device):
	display      = None
	acceleration = None # dict: different messages need different acceleration
	                    # maps so keep a mapping from message codes to arrays
	                    # of stress levels. only used for tactile events.

	def __new__(cls, wire, queue, guid):
		object = super(Classic, cls).__new__(cls, wire, queue, guid)
		Classic.__init__(object, wire, queue, guid)
		return object

	def __init__(self, wire, queue, guid):
		self.display      = Display((320,32), self.wire)
		self.acceleration = init_acceleration_maps()

	def enough_stress(self, code, stress):
		if stress == 0:
			return True # special case to catch all untracked codes
		if code in self.acceleration:
			# return true if the stress level is in the acceleration array
			# for the given code, or if the stress level is off the chart.
			if (stress in self.acceleration[code]
			or  stress > self.acceleration[code][-1]):
				return True
		return False

	def run(self):
		# Python limit: the player cannot be created in __init__() because
		# the threading would goes bananas. player contains more threads and
		# threads cannot be created "inside" the creation procedures of other
		# threads.
		self.player = Player(self.wire, self.guid)

		(guid, render, transition) = self.menu.curry()
		render.draw(self.display.canvas)
		self.display.show(transition)
		render = None

		while(self.alive):
			msg = None

			try:
				# waking up 50 times per second costs less than 1% CPU of a
				# single core in an Intel Core2 Duo system, so lets do that
				# to get good resolution in all ticking activities.
				msg = self.queue.get(block=True, timeout=0.02)
			except Exception, e:
				pass # most likely, it's just the timeout that triggered.

			if not msg:
				self.display.canvas.clear()
				(guid, render, transition) = self.menu.ticker()
				render.tick(self.display.canvas)
				self.display.show(transition)
				render = None
				continue

			try:
				if isinstance(msg, Helo):
					# always draw on screen when a device reconnects
					self.menu.draw()
				if isinstance(msg, Stat):
					if msg.event == 'STMt':
						self.player.set_progress(msg.msecs)
					else:
						print('STAT %s' % msg.event)
					continue
				if isinstance(msg, Tactile):
					# abort handling if the stress level isn't high enough.
					# note that the stress is always "enough" if stress is
					# zero or the event doesn't have a stress map at all.
					if not self.enough_stress(msg.code, msg.stress):
						continue

					print('%s %d' % (msg, abs(msg.code)))

					if msg.code == IR.UP:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.up()
						render.draw(self.display.canvas)
					elif msg.code == IR.DOWN:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.down()
						render.draw(self.display.canvas)
					elif msg.code == IR.RIGHT:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.enter()
						render.draw(self.display.canvas)
					elif msg.code == IR.LEFT:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.leave()
						render.draw(self.display.canvas)

					elif msg.code == IR.BRIGHTNESS:
						self.display.next_brightness()

					elif msg.code == IR.PLAY:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.ticker()
						if not self.player.play(guid):
							transition = TRANSITION.BOUNCE_RIGHT
						render.tick(self.display.canvas)
					elif msg.code == IR.PAUSE:
						self.player.pause()
					elif msg.code == IR.FORWARD:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.ticker()
						render.tick(self.display.canvas)
						render = ProgressRender(self.player.seek(1000))
						render.draw(self.display.canvas)
					elif msg.code == IR.REWIND:
						self.display.canvas.clear()
						(guid, render, transition) = self.menu.ticker()
						render.tick(self.display.canvas)
						render = ProgressRender(self.player.seek(-1000))
						render.draw(self.display.canvas)
					elif msg.code == -IR.FORWARD:
						print('FORWARD one track')
					elif msg.code == -IR.REWIND:
						print('REWIND one track')

					elif msg.code == IR.VOLUME_UP:
						self.player.volume_up()
					elif msg.code == IR.VOLUME_DOWN:
						self.player.volume_down()

					elif msg.code == IR.POWER or msg.code == IR.HARD_POWER:
						self.alive = False

					elif msg.code == IR.NUM_1:
						self.player.stop_playback()
					elif msg.code == IR.NUM_2:
						self.player.flush_buffer()
					elif msg.code == IR.NUM_3:
						self.player.start_playback(10)
					elif msg.code == IR.NUM_4:
						pass
					elif msg.code == IR.NUM_5:
						pass
					elif msg.code == IR.NUM_6:
						pass
					elif msg.code == IR.NUM_7:
						pass
					elif msg.code == IR.NUM_8:
						pass
					elif msg.code == IR.NUM_9:
						pass

					elif msg.code == IR.NOW_PLAYING:
						self.display.next_visualizer()

					elif msg.code < 0:
						pass

					else:
						raise Exception, ('Unhandled code %s'
						                  % IR.codes_debug[abs(msg.code)])

					if render:
						self.display.show(transition)
					render = None

			except:
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]
				self.alive = False

		self.player.close()
		print('device is Dead')
