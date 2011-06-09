# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys

from threading import Thread
from Queue     import Queue
from datetime  import datetime

from protocol  import Helo, Hail, Tactile, Stat, Listing, Terms, Dsco, Ping
from display   import Display, TRANSITION
from tactile   import IR
from menu      import Menu
from player    import Player
from seeker    import Seeker
from render    import ProgressRender, OverlayRender
from wire      import JsonWire
from cm        import ContentManager
from volume    import Volume
from watchdog  import Watchdog

class Device(Thread):
	queue    = None  # let other threads post events here
	alive    = True  # controls the main loop
	sb_wire  = None  # must have a wire to send actual commands to the device
	cm_wire  = None  # must have a wire to talk to the content manager
	menu     = None  # all devices must have a menu system
	guid     = None  # string. uniqely identifies the device. usualy MAC addr.
	player   = None
	seeker   = None
	playlist = None
	volume   = None  # Volume object
	watchdog = None

	def __init__(self, sb_wire, queue, guid, name='Device'):
		print 'Device __init__'
		Thread.__init__(self, name=name)
		self.sb_wire = sb_wire
		self.queue   = queue
		self.guid    = guid
		self.menu    = Menu()
		self.cm_wire = JsonWire(None, 3484, queue)
		self.cm_wire.start()
		self.watchdog = Watchdog(1000)

	def run(self):
		raise Exception('Device subclasses must implement run()')
	
	def stop(self):
		self.sb_wire.stop()
		self.cm_wire.stop()
		self.alive = False

def init_acceleration_maps():
	maps    = {}
	default = [0,3,6,9,12,15,18,21,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52]

	maps[IR.UP]          = default
	maps[IR.DOWN]        = default
	maps[IR.LEFT]        = default
	maps[IR.RIGHT]       = default
	maps[IR.BRIGHTNESS]  = default
	maps[IR.VOLUME_UP]   = [0]
	maps[IR.VOLUME_DOWN] = [0]
	maps[IR.FORWARD]     = [0]
	maps[IR.REWIND]      = [0]
	maps[-IR.FORWARD]    = [0]
	maps[-IR.REWIND]     = [0]
	maps[IR.NUM_0]       = default
	maps[IR.NUM_1]       = default
	maps[IR.NUM_2]       = default
	maps[IR.NUM_3]       = default
	maps[IR.NUM_4]       = default
	maps[IR.NUM_5]       = default
	maps[IR.NUM_6]       = default
	maps[IR.NUM_7]       = default
	maps[IR.NUM_8]       = default
	maps[IR.NUM_9]       = default

	return maps

class Classic(Device):
	display      = None
	acceleration = None # dict: different messages need different acceleration
	                    # maps so keep a mapping from message codes to arrays
	                    # of stress levels. only used for tactile events.

	def __init__(self, sb_wire, queue, guid):
		print 'Classic __init__'
		Device.__init__(self, sb_wire, queue, guid, 'Classic')
		self.display      = Display((320,32), sb_wire)
		self.acceleration = init_acceleration_maps()
		self.volume       = Volume(sb_wire, 255, 70, 70, True)

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
		# if the user recently manipulated the volume, check if the last
		# rendering should be kept for a little longer.
		if self.volume.timeout > datetime.now():
			return self.volume.meter
		# get the guids for the currently playing track (if any) and the
		# currently visible menu item. if they happen to be the same, then
		# prefer the rendering ticker for the currently playing track.
		(guid1, render1) = self.menu.ticker()
		(guid2, render2) = self.player.ticker()
		if guid1 == guid2:
			# the menu is focused on the currently playing track. if the user
			# is also seeking in the track, then return a NowPlaying render
			# where the normal progress bar is replaced with a seek bar.
			if self.seeker:
				(guid3, render3) = self.seeker.ticker()
				return OverlayRender(render2.base, render3)
			# just return the NowPlaying render 
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
		self.player = Player(self.sb_wire, self.guid)

		while self.alive :
			msg = None

			try:
				# waking up 50 times per second costs less than 1% CPU of a
				# single core in an Intel Core2 Duo system, so lets do that
				# to get good resolution in all ticking activities.
				msg = self.queue.get(block=True, timeout=0.02)
				self.watchdog.reset()
			except Exception, e:
				# most likely, it's just the timeout that triggered.
				if self.watchdog.wakeup():
					self.sb_wire.send(Ping().serialize())
				elif self.watchdog.expired():
					self.stop()
					continue

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


				if isinstance(msg, Hail):
					cm = ContentManager(
						msg.label, self.cm_wire, msg.stream_ip, msg.stream_port
					)
					self.menu.add_cm(cm)
					continue

				if isinstance(msg, Listing):
					parent = self.menu.focused().parent
					if parent.guid == msg.guid:
						parent.add(msg.listing)
						# redraw screen in case it was showing '<EMPTY>'
						(guid, render) = self.menu.ticker(curry=True)
						self.display.canvas.clear()
						render.tick(self.display.canvas)
						self.display.show(TRANSITION.NONE)
						continue

				if isinstance(msg, Terms):
					print('got terms')
					self.menu.searcher.add_dict_terms(msg.terms)
					continue						

				if isinstance(msg, Stat):
					next = self.player.handle_stat(msg)
					# play next item, if any. otherwise clean the display
					if next:
						while not self.player.play(next):
							next = next.next()
					if next:
						(guid, render) = self.player.ticker()
					else:
						# curry the currently focused menu item to ensure
						# that it is correctly redrawn after the track
						# stops playing
						self.menu.ticker(curry=True)
					continue

				if isinstance(msg, Dsco):
					print(str(msg))
					self.player.finish()
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
						render = self.select_render()
					elif msg.code == IR.DOWN:
						(guid, render, transition) = self.menu.down()
						render = self.select_render()
					elif msg.code == IR.RIGHT:
						(guid, render, transition) = self.menu.right()
					elif msg.code == IR.LEFT:
						(guid, render, transition) = self.menu.left()

					elif msg.code == IR.BRIGHTNESS:
						self.display.next_brightness()

					elif msg.code == IR.ADD:
						item = self.menu.focused()
						if self.menu.cwd == self.menu.playlist:
							# if the user is browsing the playlist, then ADD
							# removes the focused item.
							self.menu.playlist.remove(item)
							(guid, render) = self.menu.ticker(curry=True)
							#transition = TRANSITION.SCROLL_UP
						else:
							self.menu.playlist.add(item)

					elif msg.code == IR.PLAY:
						item = self.menu.focused()
						if not self.player.play(item):
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
							self.seeker = Seeker(self.player.playing.item,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(1000)
						render = self.select_render()
					elif msg.code == IR.REWIND:
						if not self.player.playing:
							print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.item,
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
							self.player.jump(self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							next = self.player.playing.item.next()
							if next:
								while not self.player.play(next):
									next = next.next()
							if next:
								(guid, render) = self.player.ticker()
							else:
								# curry the currently focused menu item to
								# ensure that it is correctly redrawn after
								# the track stops playing
								self.menu.ticker(curry=True)
					elif msg.code == -IR.REWIND:
						if msg.stress >= 5:
							if not self.player.playing:
								print('Nothing playing, nothing to seek in')
								continue
							self.player.jump(self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							prev = self.player.playing.item.prev()
							if prev:
								while not self.player.play(prev):
									next = next.prev()
							if prev:
								(guid, render) = self.player.ticker()
							else:
								# curry the currently focused menu item to
								# ensure that it is correctly redrawn after
								# the track stops playing
								self.menu.ticker(curry=True)

					elif msg.code == IR.VOLUME_UP:
						self.volume.up()
						render = self.volume.meter
					elif msg.code == IR.VOLUME_DOWN:
						self.volume.down()
						render = self.volume.meter

					elif msg.code == IR.POWER or msg.code == IR.HARD_POWER:
						
						pass

					elif msg.code in [IR.NUM_1, IR.NUM_2, IR.NUM_3,
					                  IR.NUM_4, IR.NUM_5, IR.NUM_6,
					                  IR.NUM_7, IR.NUM_8, IR.NUM_9]:
						(guid, render, transition) = self.menu.number(msg.code)

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
						render.tick(self.display.canvas)
						self.display.show(transition)
						render.min_timeout(325)

			except:
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]
				self.stop()

		print('device is Dead')


