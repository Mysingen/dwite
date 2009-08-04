# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys

from threading import Thread
from Queue     import Queue

from protocol  import Helo, Tactile, Stat
from display   import Display, TRANSITION
from tactile   import IR
from menu      import Menu
from player    import Player
from seeker    import Seeker
from render    import ProgressRender
from render    import OverlayRender

class Device(Thread):
	queue   = None  # let other threads post events here
	alive   = True  # controls the main loop
	wire    = None  # must have a wire to send actual commands to the device
	menu    = None  # all devices must have a menu system
	guid    = None  # string. uniqely identifies the device. usualy MAC addr.
	player  = None
	seeker  = None

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
	maps[-IR.FORWARD]    = [0]
	maps[-IR.REWIND]     = [0]

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

	def select_render(self):
		# get the guids for the currently playing track (if any) and the
		# currently visible menu item. if they happen to be the same, then
		# prefer the render for the currently playing track.
		(guid1, render1) = self.menu.ticker()
		(guid2, render2) = self.player.ticker()
		if guid1 == guid2:
			return render2
		# if the user is seeking, but the menu isn't focused on the currently
		# playing track, then get a render that is the combination of that menu
		# item's render and the render for showing the progress bar
		if self.seeker:
			(guid3, render3) = self.seeker.ticker()
			return OverlayRender(render1, render3)
		# just return the render for the currently focused menu item
		return render1

	def default_ticking(self):
		self.display.canvas.clear()
		render = self.select_render()
		if render.tick(self.display.canvas):
			self.display.show(TRANSITION.NONE)

	def run(self):
		# Python limit: the player cannot be created in __init__() because
		# the threading would goes bananas. player contains more threads and
		# threads cannot be created "inside" the creation procedures of other
		# threads.
		self.player = Player(self.wire, self.guid)

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
				self.default_ticking()
				continue

			try:
				if isinstance(msg, Helo):
					# always draw on screen when a device (re)connects
					(guid, render) = self.menu.ticker(curry=True)
					self.display.canvas.clear()
					render.tick(self.display.canvas)
					self.display.show(TRANSITION.NONE)
					continue

				if isinstance(msg, Stat):
					if msg.event == 'STMt':
						self.player.set_progress(msg.msecs)
						self.player.set_buffers(msg.in_fill, msg.out_fill)
					elif msg.event == 'STMo':
						self.player.set_progress(msg.msecs)
						self.player.set_buffers(msg.in_fill, msg.out_fill)
						self.player.finish()
						self.seeker = None
						# curry the currently focused menu item to ensure that
						# it is correctly redrawn after the track stops playing
						self.menu.ticker(curry=True)
						#print msg
					else:
						print('STAT %s' % msg.event)
					continue

				if isinstance(msg, Tactile):
					# abort handling if the stress level isn't high enough.
					# note that the stress is always "enough" if stress is
					# zero or the event doesn't have a stress map at all.
					if not self.enough_stress(msg.code, msg.stress):
						self.default_ticking()
						continue

					guid       = 0
					render     = None
					transition = TRANSITION.NONE

					if   msg.code == IR.UP:
						(guid, render, transition) = self.menu.up()
					elif msg.code == IR.DOWN:
						(guid, render, transition) = self.menu.down()
					elif msg.code == IR.RIGHT:
						(guid, render, transition) = self.menu.enter()
					elif msg.code == IR.LEFT:
						(guid, render, transition) = self.menu.leave()

					elif msg.code == IR.BRIGHTNESS:
						self.display.next_brightness()

					elif msg.code == IR.PLAY:
						(guid, render) = self.menu.ticker()
						if not self.player.play(guid):
							transition = TRANSITION.BOUNCE_RIGHT
						else:
							(guid, render) = self.player.ticker()
					elif msg.code == IR.PAUSE:
						self.player.pause()
					elif msg.code == IR.FORWARD:
						if not self.player.playing:
							print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.guid,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(1000)
						render = self.select_render()
					elif msg.code == IR.REWIND:
						if not self.player.playing:
							print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.guid,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(-1000)
						render = self.select_render()
					elif msg.code == -IR.FORWARD:
						print('-IR.FORWARD')
						if msg.stress >= 5:
							if not self.player.playing:
								print('Nothing playing, nothing to seek in')
								continue
							self.player.stop()
							self.player.play(self.seeker.guid,
							                 self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							print('FORWARD one track')
					elif msg.code == -IR.REWIND:
						if msg.stress >= 5:
							if not self.player.playing:
								print('Nothing playing, nothing to seek in')
								continue
							self.player.stop()
							self.player.play(self.seeker.guid,
							                 self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							print('REWIND one track')

					elif msg.code == IR.VOLUME_UP:
						self.player.volume_up()
					elif msg.code == IR.VOLUME_DOWN:
						self.player.volume_down()

					elif msg.code == IR.POWER or msg.code == IR.HARD_POWER:
						self.alive = False

					elif msg.code == IR.NUM_1:
						self.player.stop()
					elif msg.code == IR.NUM_2:
						pass
					elif msg.code == IR.NUM_3:
						pass
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

					#print(msg)
					if render:
						self.display.canvas.clear()
						if render.tick(self.display.canvas):
							self.display.show(transition)

			except:
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]
				self.alive = False

		self.player.close()
		print('device is Dead')

