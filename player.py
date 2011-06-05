# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import os.path

from protocol import Strm, StrmStartMpeg, StrmStop, StrmFlush, StrmSkip
from protocol import StrmPause, StrmUnpause
from render   import NowPlayingRender
from menu     import CmMp3Tree

class Player:
	guid        = None # used when telling the device how to present itself
	wire        = None
	vol_l       = 0    # percentage integer. 0 is mute? what about aude?
	vol_r       = 0    # percentage integer. 0 is mute? what about aude?
	preamp      = 255  # 0-255
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
		print('play %s' % str(item))

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
		if not self.playing:
			return
		try:
			if self.playing.paused():
				self.playing.enter_state(NowPlaying.PAUSED)
				self.wire.send(StrmPause().serialize())
			else:
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

