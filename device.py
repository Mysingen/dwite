# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import re

from threading import Thread
from Queue     import Queue
from datetime  import datetime

from protocol  import(Helo, Tactile, Stat, JsonResult, Terms, Dsco, Ping,
                      StrmStatus, Ls, Play, GetItem)
from display   import Display, TRANSITION
from tactile   import IR
from menu      import Menu, CmAudio, CmDir, make_item
from player    import Player
from seeker    import Seeker
from render    import ProgressRender, OverlayRender
from wire      import JsonWire
from volume    import Volume
from watchdog  import Watchdog
from cm        import ContentManager

# private message classes. only used to implement public API's
class AddCM:
	cm = None
	
	def __init__(self, cm):
		assert type(cm) == ContentManager
		self.cm = cm

class RemCM:
	cm = None
	
	def __init__(self, cm):
		assert type(cm) == ContentManager
		self.cm = cm

class Device(Thread):
	queue    = None  # let other threads post events here
	alive    = True  # controls the main loop
	sb_wire  = None  # must have a wire to send actual commands to the device
	menu     = None  # all devices must have a menu system
	guid     = None  # string. uniqely identifies the device. usualy MAC addr.
	player   = None
	seeker   = None
	playlist = None
	volume   = None  # Volume object
	watchdog = None
	cms      = {}

	def __init__(self, sb_wire, queue, guid, name='Device'):
		print 'Device __init__'
		Thread.__init__(self, name=name)
		self.sb_wire = sb_wire
		self.queue   = queue
		self.guid    = guid
		self.menu    = Menu()
		self.watchdog = Watchdog(1000)

	def run(self):
		raise Exception('Device subclasses must implement run()')
	
	def stop(self):
		self.sb_wire.stop()
		self.alive = False

	def add_cm(self, cm):
		self.queue.put(AddCM(cm))
	
	def rem_cm(self, cm):
		self.queue.put(RemCM(cm))

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

	def default_result_handler(self, cm, msg, orig_msg):
		if type(orig_msg) == Ls:
			parent = self.menu.focused().parent
			if parent.guid == orig_msg.item:
				parent.add(msg.result)
				# redraw screen in case it was showing '<EMPTY>'
				(guid, render) = self.menu.ticker(curry=True)
				self.display.canvas.clear()
				render.tick(self.display.canvas)
				self.display.show(TRANSITION.NONE)

	def run(self):
		# Python limit: the player cannot be created in __init__() because
		# the threading would goes bananas. player contains more threads and
		# threads cannot be created "inside" the creation procedures of other
		# threads.
		self.player = Player(self.sb_wire, self.guid)

		while self.alive:
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
				#### MESSAGES FROM PROGRAMS ####

				if isinstance(msg, AddCM):
					self.cms[msg.cm.label] = msg.cm
					self.menu.add_cm(msg.cm)
					continue

				if isinstance(msg, RemCM):
					del self.cms[msg.cm.label]
					self.menu.rem_cm(msg.cm)

				if isinstance(msg, JsonResult):
					print msg
					for cm in self.cms.values():
						if msg.guid in cm.msg_guids:
							(orig_msg, handler) = cm.get_msg_handler(msg)
							cm.rem_msg_handler(msg)
							if handler:
								handler(self, cm, msg, orig_msg)
							else:
								self.default_result_handler(cm, msg, orig_msg)
							continue

				if isinstance(msg, Terms):
					print('got terms')
					self.menu.searcher.add_dict_terms(msg.terms)
					continue						

				if isinstance(msg, Play):
					print unicode(msg)
					match = re.match(
						'(?P<scheme>^.+?)://(?P<cm>.+?)/(?P<guid>.+)', msg.url
					)
					if not match:
						errno  = 1
						errstr = (u'Invalid URL. Required format: "cm://<cm '
						       +  'label>/<guid>"')
						result = JsonResult(
							msg.guid, errno, errstr, 0, False, False
						)
						msg.wire._send(result.serialize())
						msg.wire.stop()
						continue
					scheme = match.group('scheme')
					label  = match.group('cm')
					guid   = match.group('guid')
					if scheme != u'cm':
						errno  = 2
						errstr = u'Invalid URL scheme: %s' % msg.url
						result = JsonResult(
							msg.guid, errno, errstr, 0, False, False
						)
						msg.wire._send(result.serialize())
						msg.wire.stop()
						continue
					if label not in self.cms:
						errno  = 3
						errstr = u'No such CM: %s' % label
						result = JsonResult(
							msg.guid, errno, errstr, 0, False, False
						)
						msg.wire._send(result.serialize())
						msg.wire.stop()
						continue
					cm = self.cms[label]
					get = GetItem(cm.make_msg_guid(), guid)

					def handle_get_item(self, cm, msg, orig_msg):
						if msg.errno:
							orig_msg.wire._send(msg.serialize())
							orig_msg.wire.stop()
							return
						item = make_item(cm, msg.result)
						if not self.player.play(item, orig_msg.seek):
							errno  = 4
							errstr = u'Unplayable item'
							result = JsonResult(
								orig_msg.guid, errno, errstr, 0, False, False
							)
							orig_msg.wire._send(result.serialize())
							orig_msg.wire.stop()
							return
						if item == self.menu.focused():
							(guid, render) = self.player.ticker()
							self.display.canvas.clear()
							render.tick(self.display.canvas)
							self.display.show(TRANSITION.NONE)
							render.min_timeout(325)
						result = JsonResult(
							orig_msg.guid, 0, u'EOK', 0, False, True
						)
						orig_msg.wire._send(result.serialize())
						orig_msg.wire.stop()

					cm.msg_guids[get.guid] = (msg, handle_get_item)
					cm.wire.send(get.serialize())

				#### MESSAGES FROM THE DEVICE ####

				if isinstance(msg, Helo):
					# always draw on screen when a device (re)connects
					(guid, render) = self.menu.ticker(curry=True)
					self.display.canvas.clear()
					render.tick(self.display.canvas)
					self.display.show(TRANSITION.NONE)
					continue

				if isinstance(msg, Stat):
					next = self.player.handle_stat(msg)
					# play next item, if any. otherwise clean the display
					while next and not self.player.play(next):
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
						elif isinstance(item, CmAudio):
							self.menu.playlist.add(item)
						elif isinstance(item, CmDir):
							def handle_ls_r(self, cm, response, orig_msg):
								assert type(self)     == Classic
								assert type(cm)       == ContentManager
								assert type(response) == JsonResult
								for r in response.result:
									item = make_item(cm, r)
									self.menu.playlist.add(item)
							# ask CM for a recursive listing of the directory
							# and remember the sequence number of the message
							# so that special handling can be applied to the
							# reply from CM.
							ls = Ls(item.cm.make_msg_guid(), item.guid, True)
							print unicode(ls)
							item.cm.msg_guids[ls.guid] = (ls, handle_ls_r)
							item.cm.wire.send(ls.serialize())


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
						self.seeker.seek(5000)
						render = self.select_render()
					elif msg.code == IR.REWIND:
						if not self.player.playing:
							print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.item,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(-5000)
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
							while next and not self.player.play(next):
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
							while prev and not self.player.play(prev):
								prev = prev.prev()
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
						self.stop()
						pass

					elif msg.code in [IR.NUM_1, IR.NUM_2, IR.NUM_3,
					                  IR.NUM_4, IR.NUM_5, IR.NUM_6,
					                  IR.NUM_7, IR.NUM_8, IR.NUM_9]:
						(guid, render, transition) = self.menu.number(msg.code)
						self.sb_wire.send(StrmStatus().serialize())

					elif msg.code == IR.NOW_PLAYING:
						self.display.next_visualizer()

					elif msg.code < 0:
						pass

					else:
						raise Exception, ('Unhandled code %s'
						                  % IR.codes_debug[abs(msg.code)])

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


