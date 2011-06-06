# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import os.path
import struct

from protocol import Strm, StrmStartMpeg, StrmStop, StrmFlush, StrmSkip, Stat
from protocol import StrmPause, StrmUnpause
from render   import NowPlayingRender
from menu     import CmMp3Tree

class Player:
	guid        = None # used when telling the device how to present itself
	wire        = None
	cm          = None
	playing     = None # NowPlaying instance

	def __init__(self, wire, guid):
		self.guid = guid
		self.wire = wire
		self.stop()
	
	def close(self):
		pass

	# playback manipulations

	def get_in_threshold(self, size):
		if size < 10*1024:
			tmp = size / 1024 # 'size' is a natural number so the result is too
			if tmp > 0:
				return tmp - 1
		return 10 # I'm just guessing
	
	def play(self, item, seek=0):
		if not isinstance(item, CmMp3Tree):
			return False

		# stop the currently playing track, if any
		if self.playing:
			self.stop()

		self.playing = NowPlaying(item, item.duration, seek)
		strm = StrmStartMpeg(
			item.cm.stream_ip, item.cm.stream_port, item.guid, seek
		)
		strm.in_threshold = self.get_in_threshold(item.size)
		self.wire.send(strm.serialize())
		return True

	def jump(self, position):
		item = self.playing.item
		self.wire.send(StrmStop().serialize())
		strm = StrmStartMpeg(
			item.cm.stream_ip, item.cm.stream_port, item.guid, position
		)
		strm.in_threshold = self.get_in_threshold(item.size)
		self.wire.send(strm.serialize())
		self.playing.start    = position
		self.playing.progress = 0

	def duration(self):
		return self.playing.duration
	
	def position(self):
		return self.playing.position()

#	def flush_buffer(self):
#		self.wire.send(StrmFlush().serialize())
#		self.playing = None

#	def stream_background(self):
#		strm = StrmStartMpeg(0, self.cm.port, path, True)
#		self.wire.send(strm.serialize())

	def stop(self):
		self.wire.send(StrmStop().serialize())
		self.playing = None

	def pause(self):
		print '0'
		if not self.playing:
			print '1'
			return
		try:
			if not self.playing.paused():
				print '2'
				self.playing.enter_state(NowPlaying.PAUSED)
				self.wire.send(StrmPause().serialize())
			else:
				print '3'
				self.playing.enter_state(NowPlaying.BUFFERING)
				self.wire.send(StrmUnpause().serialize())
		except Exception, e:
			print e

#	def skip(self, msecs):
#		if self.playing.state != NowPlaying.PLAYING:
#			return
#		self.wire.send(StrmSkip(msecs).serialize())

	def set_progress(self, msecs):
		if not self.playing:
			return
		self.playing.set_progress(msecs)

	def get_progress(self):
		return self.playing.position()

	def set_buffers(self, in_fill, out_fill):
		pass
		#print('in/out = %d/%d' % (in_fill, out_fill))

	def finish(self):
		self.playing = None
	
	def ticker(self):
		if self.playing:
			return self.playing.curry()
		else:
			return (None, None)

	def handle_stat(self, stat):
		if not isinstance(stat, Stat):
			raise Exception('Invalid Player.handle_stat(stat): %s' % str(stat))
		if stat.event == 'STMt':
			# SBS sources calls this the "timer" event. it seems to mean that
			# the device has a periodic timeout going, because the STMt is sent
			# with an interval of about 1-2 seconds. the interesting content is
			# buffer fullness (which should perhaps be tracked by the server).
			self.set_progress(stat.msecs)
			self.set_buffers(stat.in_fill, stat.out_fill)
			return None
		if stat.event == 'STMo':
			# find next item to play, if any
			next = self.playing.item.next()
			# finish the currently playing track
			self.set_progress(stat.msecs)
			self.set_buffers(stat.in_fill, stat.out_fill)
			self.finish()
			return next

		# not terribly interesting events:
		if stat.event == '\0\0\0\0':
			print('Device is alive')
			# undocumented but always received right after the device connects
			# to the server. probably just a state indication without any event
			# semantics.
			return None
		if stat.event == 'STMf':
			# SBS sources say "closed", but this makes no sense as it will be
			# received whether the device was previously connected to a streamer
			# or not. it's also not about flushed buffers as those are typically
			# reported as unaffected.
			print('Device closed the stream connection')
			return None
		if stat.event == 'STMc':
			# SBS sources say this means "connected", but to what? probably the
			# streamer even though it is received before ACK of strm command.
			print('Device connected to streamer')
			return None
		if stat.event == 'STMe':
			# connection established with streamer. i.e. more than just an open
			# socket.
			print('Device established connection to streamer')
			return None
		if stat.event == 'STMh':
			# "end of headers", but which ones? probably the header sent by the
			# streamer in response to HTTP GET.
			print('Device finished reading headers')
			return None
		if stat.event == 'STMs':
			print('Device started playing')
			self.playing.enter_state(NowPlaying.PLAYING)
			return None
		if stat.event == 'STMp':
			print('Device paused playback')
			return None
		if stat.event == 'STMr':
			print('Device resumed playback')
			return None

		# simple ACKs of commands sent to the device. ignore:
		if stat.event in ['strm', 'aude', 'audg']:
			return None
		
		bytes = struct.unpack('%dB' % len(stat.event), stat.event)
		print('UNHANDLED STAT EVENT: %s' % str(bytes))
		print str(stat)
		return None		
	
class NowPlaying:
	# state definitions
	BUFFERING = 0 # forced pause to give a device's buffers time to fill up
	PLAYING   = 1
	PAUSED    = 2

	item     = None # playable menu item (e.g. an CmMp3Tree object)
	render   = None
	state    = BUFFERING
	start    = 0 # current playback position (in milliseconds) is calculated
	progress = 0 # as the start position plus the progress. position should
	duration = 0 # of course never be greater than the duration.
	
	def __init__(self, item, duration, start=0):
		self.item     = item
		self.duration = duration
		self.start    = start
		self.render   = NowPlayingRender(item.label)

	def	enter_state(self, state):
		if state == self.state:
			return

		if state == NowPlaying.BUFFERING:
			if ((self.state != NowPlaying.PLAYING)
			and (self.state != NowPlaying.PAUSED)):
				raise Exception, 'Must enter BUFFERING from PLAYING or PAUSED'
		elif state == NowPlaying.PLAYING:
			if ((self.state != NowPlaying.BUFFERING)
			and (self.state != NowPlaying.PAUSED)):
				raise Exception, 'Must enter PLAYING from BUFFERING or PAUSED'
		elif state == NowPlaying.PAUSED:
			if self.state != NowPlaying.PLAYING:
				raise Exception, 'Must enter PAUSED from PLAYING'
		elif state == NowPlaying.STOPPED:
			pass

		self.state = state

	def set_progress(self, progress):
		self.enter_state(NowPlaying.PLAYING)
		self.progress = progress

	def paused(self):
		return self.state == NowPlaying.PAUSED
	
	def position(self):
		return self.start + self.progress

	def curry(self):
		self.render.curry(self.position() / float(self.duration))
		return (self.item.guid, self.render)

