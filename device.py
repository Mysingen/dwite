# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import re
import os
import json
import time

from threading import Thread
from Queue     import Queue, Empty
from datetime  import datetime

from protocol  import(Helo, Tactile, Stat, JsonResult, Terms, Dsco, Ping,
                      StrmStatus, Ls, GetItem, ID, JsonMessage, Resp, Anic)
from display   import Display, TRANSITION, BRIGHTNESS
from tactile   import IR
from menu      import Menu, CmFile, CmAudio, CmDir, make_item
from player    import Player
from seeker    import Seeker
from render    import ProgressRender, OverlayRender
from wire      import JsonWire
from volume    import Volume
from cm        import CmConnection

class POWER:
	ON    = 1
	OFF   = 2
	SLEEP = 3

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
	power     = POWER.ON
	rebooting = False

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
		from dwite import register_dm
		while self.alive:
			msg = None
			try:
				msg = self.in_queue.get(block=True, timeout=0.1)
			except Empty:
				if not self.wire.is_alive():
					self.stop(hard=True)
				continue
			if type(msg) == Helo:
				# now we get to know what kind of device class we *really*
				# should have used. create it and pass the Helo message to it.
				if (msg.id == ID.SQUEEZEBOX3
				or  msg.id == ID.SOFTSQUEEZE):
					dm = Classic(self.wire, self.out_queue, msg.mac_addr)
					try:
						register_dm(dm, msg.mac_addr)
					except:
						dm.stop(hard=True)
						return
					dm.start()
					dm.in_queue.put(msg)
					self.alive = False
			else:
				print 'UNHANDLED MESSAGE: %s' % msg
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

	maps[IR.POWER]       = [0]
	maps[-IR.POWER]      = [0]
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
	_now_playing_mode = False

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
		self.player     = Player(self.wire, self.mac_addr, **settings['player'])

	@property
	def now_playing_mode(self):
		return self._now_playing_mode

	@now_playing_mode.setter
	def now_playing_mode(self, value):
		assert type(value) == bool
		if value:
			if self._now_playing_mode:
				# cycle through visualization modes
				self.display.next_visualizer()
			else:
				self.display.visualizer_on()
		else:
			self.display.visualizer_off()
		self._now_playing_mode = value

	def select_now_playing_mode(self):
		if not self.player.playing:
			self.now_playing_mode = False
			return
		if self.player.playing.item == self.menu.focused():
			if not self.now_playing_mode:
				self.now_playing_mode = True
			return
		self.now_playing_mode = False

	def load_settings(self):
		result = {}
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'dwite.json')
		settings = {}
		if os.path.exists(path):
			f = open(path)
			try:
				settings = json.load(f)
			except:
				print('ERROR: Could not load settings file %s' % path)
				settings = {}
			f.close()

		# some settings are common to all players. fill in default settings
		# if necessary:
		if 'player' in settings:
			result['player'] = settings['player']
		else:
			result['player'] = Player.dump_defaults()

		try:
			settings = settings['devices'][self.mac_addr]
		except:
			print('ERROR: Could not load settings for %s' % self.mac_addr)

		# per-device settings are indexed by MAC address. fill in default
		# settings if necessary:
		if 'display' in settings:
			result['display'] = settings['display']
		else:
			result['display'] = Display.dump_defaults()

		if 'volume' in settings:
			result['volume'] = settings['volume']
		else:
			result['volume'] = Volume.dump_defaults()

		return result

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
		storage['player'] = self.player.dump_settings()
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
		if self.power in [POWER.OFF, POWER.SLEEP]:
			return
		self.display.canvas.clear()
		render = self.select_render()
		if render.tick(self.display.canvas):
			self.display.show(TRANSITION.NONE)

	def default_result_handler(self, msg, orig_msg):
		if msg.errno:
			print msg.errstr
			return
		if type(orig_msg) == Ls:
			if orig_msg.parent:
				stay_focused = False
				# the result is a listing of the contents of the *parent* of
				# the item mentioned in the original message. reparent that
				# item in a new CmDir populated with the results.
				# if the item is neither focused nor currently playing, then
				# there is nothing to do. the user navigated away and we can
				# simply throw away the result.
				item = self.menu.focused()
				if item.guid == orig_msg.item:
					stay_focused = True
				else:
					item = self.player.get_playing()
				if item.guid != orig_msg.item:
					return # give up
				if not msg.result['item']['guid']:
					# parent is the menu root's CM widget
					parent = self.menu.get_item(item.cm.label)
					if not parent:
						return # CM no longer registered. give up.
				else:
					parent = make_item(item.cm.label, **msg.result['item'])
				parent.children = []
				parent.add(msg.result['contents'])
				item.parent = parent
				if stay_focused:
					self.menu.set_focus(item)
				# the following is necessary if the item is both focused and
				# playing. then only the focused item has been reparented but
				# the playing item needs reparenting too. otherwise the next
				# track to play will not be found when it plays to finish.
				if self.player.get_playing().guid == item.guid:
					self.player.playing.item = item
				return

			parent = self.menu.focused().parent
			if parent.guid == orig_msg.item:
				parent.add(msg.result['contents'])
				# redraw screen in case it was showing '<EMPTY>'
				(guid, render) = self.menu.ticker(curry=True)
				self.display.canvas.clear()
				render.tick(self.display.canvas)
				self.display.show(TRANSITION.NONE)
				

	def run(self):
		from dwite import unregister_dm, get_cm, msg_reg

		# don't load the playlist in __init__() which is used on speculation
		# that the resulting DM will be usable. this will happen a lot while
		# rebooting, so do it here instead to avoid useless work (loading the
		# playlist can be expensive if it is really long).
		playlist = self.load_playlist()
		for obj in playlist:
			try:
				item = make_item(**obj)
				self.menu.playlist.add(item)
			except Exception, e:
				print e
				print('Malformed playlist item: %s' % obj)

		while self.alive:
			msg = None

			guid       = 0
			render     = None
			transition = TRANSITION.NONE

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

				elif isinstance(msg, RemCM):
					self.menu.rem_cm(msg.cm)
					continue

				#### MESSAGES FROM OTHER PROGRAMS/SUBSYSTEMS ####

				elif isinstance(msg, JsonResult):
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

				elif isinstance(msg, Terms):
					self.menu.searcher.add_terms(msg.sender,msg.params['terms'])
					continue						

				elif isinstance(msg, PlayItem):
					if self.power == POWER.OFF:
						msg.respond(4, u'Device is powered off', 0,False,False)
						continue
					if self.power == POWER.SLEEP:
						self.display.set_brightness(self.display.brightness)

					#print 'dm PlayItem %s' % msg
					if not self.player.play(msg.item, msg.seek):
						msg.respond(4, u'Unplayable item', 0, False, False)
						continue
					if msg.item == self.menu.focused():
						(guid, render) = self.player.ticker()
						self.display.canvas.clear()
						render.tick(self.display.canvas)
						self.display.show(TRANSITION.NONE)
						render.min_timeout(325)
					msg.respond(0, u'EOK', 0, False, True)

					if msg.item.parent:
						continue
					# items played through RPC have no parent set and we
					# have to rebuild the parent chain. otherwise browsing
					# won't work afterwards. this is tricky. we don't even
					# know the guid of the parent. start by making a dummy
					# parent so that we can at least refocus the menu while
					# sorting out the real parent details in the background.
					msg.item.parent = CmDir(
						u'<DUMMY>', u'<WAITING>', None, msg.item.cm_label
					)
					msg.item.parent.children = [msg.item]

					# now fix the problem for real. ask the CM to list the
					# parent of the item. it is done asynchronously so it
					# will not affect the responsiveness of pressing NOW
					# PLAYING, but browsing immediately afterwards will lag
					# if it takes a long time to complete the Ls request.
					ls = Ls(msg_reg.make_guid(), msg.item.guid, parent=True)

					# warning: handler executed by CM thread:
					def handle_ls(msg_reg, response, orig_msg, self):
						msg_reg.set_handler(orig_msg, None, None)
						self.in_queue.put(response)

					msg_reg.set_handler(ls, handle_ls, self)
					msg.item.cm.wire.send(ls.serialize())
					continue

				elif isinstance(msg, AddItem):
					#print 'dm AddItem %s' % msg
					item = msg.item
					if isinstance(item, CmAudio):
						self.menu.playlist.add(item)
					elif isinstance(item, CmDir):
						# ask CM for a recursive listing of the directory
						# and remember the sequence number of the message
						# so that special handling can be applied to the
						# reply from CM.
						ls = Ls(msg_reg.make_guid(), item.guid, recursive=True)

						# warning: handler executed by CM thread:
						def handle_ls_r(msg_reg, response, orig_msg, user):
							(dm, cm) = user
							assert type(dm)       == Classic
							assert type(cm)       == CmConnection
							assert type(response) == JsonResult
							for r in response.result['contents']:
								item = make_item(cm.label, **r)
								if type(item) == CmAudio:
									dm.in_queue.put(AddItem(None, None, item))
	
						msg_reg.set_handler(ls, handle_ls_r, (self, item.cm))
						item.cm.wire.send(ls.serialize())
					if self.menu.focused() == self.menu.playlist.children[0]:
						# render the screen just in case the added items
						# replaced a focused <EMPTY> object.
						(guid, render) = self.menu.ticker(curry=True)
					msg.respond(0, u'EOK', 0, False, True)

				#### MESSAGES FROM THE DEVICE ####

				elif isinstance(msg, Helo):
					# always draw on screen when a device connects
					(guid, render) = self.menu.ticker(curry=True)
					self.display.canvas.clear()
					render.tick(self.display.canvas)
					self.display.show(TRANSITION.NONE)
					continue

				elif isinstance(msg, Stat):
					next = self.player.handle_stat(msg)
					# play next item, if any. otherwise clean the display
					while next and not self.player.play(next):
						next = next.next(self.player.repeat,self.player.shuffle)
					if next:
						if self.now_playing_mode:
							self.menu.set_focus(next)
							transition = TRANSITION.SCROLL_UP
							(guid, render) = self.player.ticker()
						else:
							self.select_now_playing_mode()

				elif isinstance(msg, Dsco):
					print msg
					self.player.stop()
					continue

				elif isinstance(msg, Anic):
					continue # don't care

				elif isinstance(msg, Resp):
					self.player.handle_resp(msg)
					continue

				elif isinstance(msg, Tactile):
					# is the device powered up? if not, discard all messages
					# except POWER ON.
					if self.power == POWER.OFF and abs(msg.code) != IR.POWER:
						continue

					# abort handling if the stress level isn't high enough.
					# note that the stress is always "enough" if stress is
					# zero or the event doesn't have a stress map at all.
					if not self.enough_stress(msg.code, msg.stress):
						self.default_ticking()
						continue

					if self.power == POWER.SLEEP:
						self.power = POWER.ON
						self.player.pause()
						self.display.set_brightness(self.display.brightness)
						self.default_ticking()
						continue

					if   msg.code == IR.UP:
						(guid, render, transition) = self.menu.up()
						render = self.select_render()
						self.select_now_playing_mode()

					elif msg.code == IR.DOWN:
						(guid, render, transition) = self.menu.down()
						render = self.select_render()
						self.select_now_playing_mode()

					elif msg.code == IR.RIGHT:
						focused = self.menu.focused()
						if type(focused) == CmDir:
							ls = Ls(msg_reg.make_guid(), focused.guid)
						
							# warning: handler executed by CM thread:
							def handle_ls(msg_reg, response, orig_msg, self):
								msg_reg.set_handler(orig_msg, None, None)
								self.in_queue.put(response)

							msg_reg.set_handler(ls, handle_ls, self)
							focused.cm.wire.send(ls.serialize())
						(guid, render, transition) = self.menu.right()
						self.select_now_playing_mode()

					elif msg.code == IR.LEFT:
						focused = self.menu.focused()
						ls      = None

						if (self.menu.cwd != self.menu.root
						and type(focused.parent) == CmDir
						and focused.parent.parent == None):
							# parent may be None because navigation started
							# from a leaf item instead of from the menu root.
							# this happens e.g. when RPC was used to play an
							# item and then NOW PLAYING was pressed on the
							# remote.
							if focused.parent.guid == u'<DUMMY>':
								# if the focused item is in the process of
								# being reparented, then we have to wait for
								# that to finish. otherwise we will request
								# the DUMMY guid from the CM (because that is
								# the temporary parent to be replaced). just
								# pretend that the user didn't press the key:
								continue
							focused.parent.parent = CmDir(
								u'<DUMMY>', u'<WAITING>', None, focused.cm_label
							)
							focused.parent.parent.children = [focused.parent]

							ls = Ls(
								msg_reg.make_guid(),
								focused.parent.guid,
								parent=True
							)
						
							# warning: handler executed by CM thread:
							def handle_ls(msg_reg, response, orig_msg, self):
								msg_reg.set_handler(orig_msg, None, None)
								self.in_queue.put(response)
							
							msg_reg.set_handler(ls, handle_ls, self)
							#focused.cm.wire.send(ls.serialize())
						(guid, render, transition) = self.menu.left()
						if ls:
							focused.cm.wire.send(ls.serialize())
						self.select_now_playing_mode()

					elif msg.code == IR.BRIGHTNESS:
						self.display.next_brightness()

					elif msg.code == IR.ADD:
						item = self.menu.focused()
						if self.menu.cwd == self.menu.playlist:
							# if the user is browsing the playlist, then ADD
							# removes the focused item. check for next item to
							# play before removing it. otherwise the next item
							# can't be found.
							next = None
							if self.player.get_playing() == item:
								self.player.stop()
								wrap   = self.player.repeat
								random = self.player.shuffle
								next   = item.next(wrap, random)
								while next and not self.player.play(next):
									next = next.next(wrap, random)
							self.menu.playlist.remove(item)
							if next and next != item:
								self.menu.set_focus(next)
								transition = TRANSITION.SCROLL_UP
								(guid, render) = self.player.ticker()
							else:
								# curry the currently focused menu item to
								# ensure that it is correctly redrawn after
								# the track stops playing
								(guid, render) = self.menu.ticker(curry=True)
							self.select_now_playing_mode()
							#transition = TRANSITION.SCROLL_UP
						elif isinstance(item, CmAudio):
							self.menu.playlist.add(item)
						elif isinstance(item, CmDir):
							# ask CM for a recursive listing of the directory
							# and remember the sequence number of the message
							# so that special handling can be applied to the
							# reply from CM.
							ls = Ls(
								msg_reg.make_guid(), item.guid, recursive=True
							)

							# warning: handler executed by CM thread:
							def handle_ls_r(msg_reg, response, orig_msg, user):
								(dm, cm) = user
								assert type(dm)       == Classic
								assert type(cm)       == CmConnection
								assert type(response) == JsonResult
								for r in response.result['contents']:
									item = make_item(cm.label, **r)
									if type(item) == CmAudio:
										dm.in_queue.put(AddItem(None,None,item))

							msg_reg.set_handler(ls, handle_ls_r, (self,item.cm))
							item.cm.wire.send(ls.serialize())

					elif msg.code == IR.PLAY:
						item = self.menu.focused()
						if self.player.play(item):
							self.now_playing_mode = True
							(guid, render) = self.player.ticker()
						else:
							(guid, render, transition) = self.menu.play()

					elif msg.code == IR.PAUSE:
						self.player.pause()

					elif msg.code == IR.FORWARD:
						if not self.player.playing:
							#print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.item,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(5000)
						render = self.select_render()

					elif msg.code == IR.REWIND:
						if not self.player.playing:
							#print('Nothing playing, nothing to seek in')
							continue
						if not self.seeker:
							self.seeker = Seeker(self.player.playing.item,
							                     self.player.duration(),
							                     self.player.position())
						self.seeker.seek(-5000)
						render = self.select_render()

					elif msg.code == -IR.FORWARD:
						if msg.stress >= 5:
							if not self.player.playing:
								#print('Nothing playing, nothing to seek in')
								continue
							self.player.jump(self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							if not self.player.playing:
								continue
							wrap   = self.player.repeat
							random = self.player.shuffle
							next   = self.player.get_playing().next(wrap,random)
							while next and not self.player.play(next):
								next = next.next(wrap, random)
							if next:
								if self.now_playing_mode:
									self.menu.set_focus(next)
									transition = TRANSITION.SCROLL_UP
									(guid, render) = self.player.ticker()
							else:
								# curry the currently focused menu item to
								# ensure that it is correctly redrawn after
								# the track stops playing
								self.menu.ticker(curry=True)
							self.select_now_playing_mode()

					elif msg.code == -IR.REWIND:
						if msg.stress >= 5:
							if not self.player.playing:
								#print('Nothing playing, nothing to seek in')
								continue
							self.player.jump(self.seeker.position)
							self.seeker = None
							# curry the focused menu item to ensure that it
							# is correctly redrawn without a progres bar:
							self.menu.ticker(curry=True)
						else:
							if not self.player.playing:
								continue
							wrap   = self.player.repeat
							random = self.player.shuffle
							prev   = self.player.get_playing().prev(wrap,random)
							while prev and not self.player.play(prev):
								prev = prev.prev(wrap, random)
							if prev:
								if self.now_playing_mode:
									self.menu.set_focus(prev)
									transition = TRANSITION.SCROLL_DOWN
									(guid, render) = self.player.ticker()
							else:
								# curry the currently focused menu item to
								# ensure that it is correctly redrawn after
								# the track stops playing
								self.menu.ticker(curry=True)
							self.select_now_playing_mode()

					elif msg.code == IR.VOLUME_UP:
						self.volume.up()
						render = self.volume.meter

					elif msg.code == IR.VOLUME_DOWN:
						self.volume.down()
						render = self.volume.meter

					elif msg.code == -IR.POWER:
						self.rebooting = False
						# short button press
						if self.power == POWER.ON:
							self.wire.log = True
							self.player.stop()
							self.select_now_playing_mode()
							self.volume.mute(True)
							self.display.set_brightness(BRIGHTNESS.OFF, False)
							self.save_settings()
							self.save_playlist()
							self.power = POWER.OFF
						else:
							self.wire.log = False
							self.power = POWER.ON
							self.volume.mute(False)
							self.display.clear()
							time.sleep(0.1) # TODO: wait for ANIC instead
							self.display.set_brightness(self.display.brightness)
							self.menu.set_focus(self.menu.get_item('Playlist'))
							(guid, render) = self.menu.ticker(curry=True)
							transition = TRANSITION.SCROLL_UP

					elif msg.code == IR.POWER:
						# long button press. stop DM if stress is high enough
						if msg.stress > 20:
							self.rebooting = True

					elif msg.code in [IR.NUM_1, IR.NUM_2, IR.NUM_3,
					                  IR.NUM_4, IR.NUM_5, IR.NUM_6,
					                  IR.NUM_7, IR.NUM_8, IR.NUM_9]:
						(guid, render, transition) = self.menu.number(msg.code)
						self.wire.send(StrmStatus().serialize())

					elif msg.code == IR.NOW_PLAYING:
						if not self.player.playing:
							continue

						item = self.player.playing.item
						if not item.parent:
							# in principle, it is not possible for an item to
							# not have a parent even if it is played through
							# RPC. *however*, because the item is reparented
							# asynchronously in the RPC case, the user could
							# possibly manage to hit NOW PLAYING before the
							# item has been reparented.
							continue
						self.menu.set_focus(item)
						self.now_playing_mode = True
						continue

					elif msg.code == IR.SEARCH:
						self.menu.set_focus(self.menu.searcher.children[0])
						self.select_now_playing_mode()
						(guid, render) = self.menu.ticker(curry=True)

					elif msg.code == IR.REPEAT:
						self.player.toggle_repeat()

					elif msg.code == IR.SHUFFLE:
						self.player.toggle_shuffle()

					elif msg.code == IR.BROWSE:
						self.menu.set_focus(self.menu.root.children[0])
						self.select_now_playing_mode()
						(guid, render) = self.menu.ticker(curry=True)

					elif msg.code == IR.SLEEP:
						if self.power == POWER.ON:
							self.power = POWER.SLEEP
							self.player.pause()
							self.display.set_brightness(BRIGHTNESS.OFF, False)

					elif msg.code == IR.SIZE:
						if self.menu.focused() == self.player.get_playing():
							self.player.next_render_mode()
							(guid, render) = self.player.ticker(curry=True)
						else:
							self.menu.next_render_mode()
							(guid, render) = self.menu.ticker(curry=True)

					elif msg.code == IR.FAVORITES:
						print('FAVORITES not handled')

					elif msg.code < 0:
						pass

					else:
						raise Exception, ('Unhandled code %s'
						                  % IR.codes_debug[abs(msg.code)])

				else:
					print('Unhandled message: %s' % msg)

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

