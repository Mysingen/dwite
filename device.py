# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import re
import os
import json

from threading import Thread
from Queue     import Queue, Empty
from datetime  import datetime

from protocol  import(Helo, Tactile, Stat, JsonResult, Terms, Dsco, Ping,
                      StrmStatus, Ls, GetItem, ID, JsonMessage)
from display   import Display, TRANSITION
from tactile   import IR
from menu      import Menu, CmFile, CmAudio, CmDir, make_item
from player    import Player
from seeker    import Seeker
from render    import ProgressRender, OverlayRender
from wire      import JsonWire
from volume    import Volume
from cm        import CmConnection

# private message classes. only used to implement public API's
class AddCM:
	def __init__(self, cm):
		assert type(cm) == CmConnection
		self.cm = cm

class RemCM:
	def __init__(self, cm):
		assert type(cm) == CmConnection
		self.cm = cm

class PlayItem(JsonMessage):
	def __init__(self, guid, wire, item, seek):
		assert type(wire) == JsonWire
		assert isinstance(item, CmFile)
		assert type(seek) == int
		self.guid = guid
		self.item = item
		self.seek = seek
		self.wire = wire
	
	def dump(self):
		r = JsonMessage.dump(self)
		r.update({
			'method': u'play_item',
			'item'  : self.item.guid,
			'seek'  : self.seek
		})
		return r

class AddItem(JsonMessage):
	def __init__(self, guid, wire, item):
		assert (not wire) or (type(wire) == JsonWire)
		assert isinstance(item, CmFile)
		self.guid = guid
		self.wire = wire
		self.item = item
	
	def dump(self):
		r = JsonMessage.dump(self)
		r.update({
			'method': u'add_item',
			'item'  : self.item.guid
		})
		return r

class Device(Thread):
	in_queue  = None  # let other threads post events here
	out_queue = None
	alive     = True  # controls the main loop
	wire      = None  # must have a wire to send actual commands to the device
	menu      = None  # all devices must have a menu system. TODO: really?
	mac_addr  = None  # string. uniqely identifies the device
	player    = None
	seeker    = None
	playlist  = None
	volume    = None  # Volume object
	watchdog  = None

	def __init__(self, wire, out_queue):
		#print 'Device __init__'
		Thread.__init__(self, name='Device')
		self.wire      = wire
		self.in_queue  = self.wire.out_queue
		self.out_queue = out_queue
		self.menu      = Menu()

	def load_settings(self):
		# Devics is a virtual class and does not load or save settings.
		# concrete classes must do it though
		raise Exception('Device classes must implement load_settings()')

	def save_settings(self):
		raise Exception('Device classes must implement load_settings()')

	def load_playlist(self):
		raise Exception('Device classes must implement load_playlist()')
	
	def save_playlist(self):
		raise Exception('Device classes must implement save_playlist()')

	def run(self):
		while self.alive:
			msg = None
			try:
				msg = self.in_queue.get(block=True, timeout=0.1)
			except Empty:
				continue
			if type(msg) == Helo:
				# now we get to know what kind of device class we *really*
				# should have used. create it and pass the Helo message to it.
				if (msg.id == ID.SQUEEZEBOX3
				or  msg.id == ID.SOFTSQUEEZE):
					dm = Classic(self.wire, self.out_queue, msg.mac_addr)
					dm.start()
					dm.in_queue.put(msg)
					self.alive = False
		#print 'Temporary %s is dead' % self.name
	
	def stop(self, hard=False):
		self.wire.stop(hard)
		self.alive = False
		self.save_settings()
		self.save_playlist()

	def add_cm(self, cm):
		self.in_queue.put(AddCM(cm))

	def rem_cm(self, cm):
		self.in_queue.put(RemCM(cm))

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

	def __init__(self, wire, out_queue, mac_addr):
		#print 'Classic __init__'
		assert type(mac_addr) == unicode
		Device.__init__(self, wire, out_queue)
		self.name         = 'Classic' # Thread member
		self.mac_addr     = mac_addr
		settings          = self.load_settings()
		self.display      = Display((320,32), wire, **settings['display'])
		self.acceleration = init_acceleration_maps()
		self.volume       = Volume(wire, **settings['volume'])
		playlist          = self.load_playlist()
		for obj in playlist:
			try:
				item = make_item(**obj)
				self.menu.playlist.add(item)
			except Exception, e:
				print e
				print('Malformed playlist item: %s' % obj)

	def load_settings(self):
		# device settings indexed by MAC address
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'dwite.json')
		settings = {}
		if os.path.exists(path):
			f = open(path)
			try:
				settings = json.load(f)['devices'][self.mac_addr]
			except:
				print('ERROR: Could not load settings for %s' % self.mac_addr)
				settings = {}
			f.close()
		# fill in default settings
		if 'display' not in settings:
			settings['display'] = Display.dump_defaults()
		if 'volume' not in settings:
			settings['volume'] = Volume.dump_defaults()
		return settings

	def save_settings(self):
		# device settings indexed by MAC address
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'dwite.json')
		try:
			f = open(path)
			storage = json.load(f)
			f.close()
		except:
			storage = {'devices':{}}
		settings = {}
		settings['volume']  = self.volume.dump_settings()
		settings['display'] = self.display.dump_settings()
		storage['devices'][self.mac_addr] = settings
		f = open(path, 'w')
		json.dump(storage, f, indent=4)
		f.close()

	def save_playlist(self):		
		# the global playlist
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'playlist.json')
		f = open(path, 'w')
		json.dump(self.menu.playlist.dump(), f, indent=4)
		f.close()

	def load_playlist(self):
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'playlist.json')
		if not os.path.exists(path):
			return []
		f = open(path)
		playlist = json.load(f)
		f.close()
		return playlist

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

	def default_result_handler(self, msg, orig_msg):
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
		from dwite import register_dm, unregister_dm, get_cm, msg_reg

		# Python limit: the player cannot be created in __init__() because
		# the threading would goes bananas. player contains more threads and
		# threads cannot be created "inside" the creation procedures of other
		# threads.
		self.player = Player(self.wire, self.mac_addr)

		while self.alive:
			msg = None

			try:
				# waking up 50 times per second costs less than 1% CPU of a
				# single core in an Intel Core2 Duo system, so lets do that
				# to get good resolution in all ticking activities.
				msg = self.in_queue.get(block=True, timeout=0.02)
			except Empty:
				if not self.wire.is_alive():
					self.stop(hard=True)
				else:
					self.default_ticking()
				continue
			except:
				traceback.print_exc()
				self.stop(hard=True)
				continue

			try:
				#### MESSAGES FROM THE DWITE'S MAIN LOOP ####

				if isinstance(msg, AddCM):
					self.menu.add_cm(msg.cm)
					continue

				if isinstance(msg, RemCM):
					self.menu.rem_cm(msg.cm)
					continue

				#### MESSAGES FROM OTHER PROGRAMS/SUBSYSTEMS ####

				if isinstance(msg, JsonResult):
					#print 'dm JsonResult %d' % msg.guid
					try:
						msg_reg.run_handler(msg)
					except:
						(orig_msg, handler, user) = msg_reg.get_handler(msg)
						if orig_msg:
							msg_reg.rem_handler(orig_msg)
							self.default_result_handler(msg, orig_msg)
							continue
						else:
							print 'throwing away %s' % msg

				if isinstance(msg, Terms):
					print('got terms')
					self.menu.searcher.add_dict_terms(msg.terms)
					continue						

				if isinstance(msg, PlayItem):
					#print 'dm PlayItem %s' % msg
					if not self.player.play(msg.item, msg.seek):
						errstr = u'Unplayable item'
						msg.respond(4, errstr, 0, False, False)
						continue
					if msg.item == self.menu.focused():
						(guid, render) = self.player.ticker()
						self.display.canvas.clear()
						render.tick(self.display.canvas)
						self.display.show(TRANSITION.NONE)
						render.min_timeout(325)
					msg.respond(0, u'EOK', 0, False, True)
					continue

				if isinstance(msg, AddItem):
					#print 'dm AddItem %s' % msg
					item = msg.item
					if isinstance(item, CmAudio):
						self.menu.playlist.add(item)
					elif isinstance(item, CmDir):
						# ask CM for a recursive listing of the directory
						# and remember the sequence number of the message
						# so that special handling can be applied to the
						# reply from CM.
						ls = Ls(msg_reg.make_guid(), item.guid, True)

						# warning: handler executed by CM thread:
						def handle_ls_r(msg_reg, response, orig_msg, user):
							(dm, cm) = user
							assert type(dm)       == Classic
							assert type(cm)       == CmConnection
							assert type(response) == JsonResult
							for r in response.result:
								item = make_item(cm.label, **r)
								if type(item) == CmAudio:
									dm.in_queue.put(AddItem(None, None, item))
	
						msg_reg.set_handler(ls, handle_ls_r, (self, item.cm))
						item.cm.wire.send(ls.serialize())
					msg.respond(0, u'EOK', 0, False, True)

				#### MESSAGES FROM THE DEVICE ####

				if isinstance(msg, Helo):
					try:
						register_dm(self, self.mac_addr)
					except Exception, e:
						print e
						self.stop()
						continue
					# always draw on screen when a device connects
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
					print msg
					self.player.stop()
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
						focused = self.menu.focused()
						if type(focused) == CmDir:
							ls = Ls(msg_reg.make_guid(), focused.guid, False)
						
							# warning: handler executed by CM thread:
							def handle_ls(msg_reg, response, orig_msg, self):
								msg_reg.set_handler(orig_msg, None, None)
								self.in_queue.put(response)

							msg_reg.set_handler(ls, handle_ls, self)
							focused.cm.wire.send(ls.serialize())
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
							# ask CM for a recursive listing of the directory
							# and remember the sequence number of the message
							# so that special handling can be applied to the
							# reply from CM.
							ls = Ls(msg_reg.make_guid(), item.guid, True)

							# warning: handler executed by CM thread:
							def handle_ls_r(msg_reg, response, orig_msg, user):
								(dm, cm) = user
								assert type(dm)       == Classic
								assert type(cm)       == CmConnection
								assert type(response) == JsonResult
								for r in response.result:
									item = make_item(cm.label, **r)
									if type(item) == CmAudio:
										dm.in_queue.put(AddItem(None,None,item))

							msg_reg.set_handler(ls, handle_ls_r, (self,item.cm))
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
							if not self.player.playing:
								continue
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
							if not self.player.playing:
								continue
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
						self.wire.send(StrmStatus().serialize())

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
				traceback.print_exc()
				self.stop()

		#print('Classic %s is Dead' % self.mac_addr)
		unregister_dm(self.mac_addr)

