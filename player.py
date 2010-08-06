# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import traceback
import sys
import os.path

from protocol import Strm, StrmStartMpeg, StrmStop, StrmFlush, StrmSkip
from protocol import Aude, Audg, StrmPause, StrmUnpause
from render   import NowPlayingRender
from menu     import CmMp3Tree

class Player:
	guid        = None # used when telling the device how to present itself
	wire        = None
	gain_l      = (0,0) # 16bit.16bit fixed point, expressed as two uint16's
	gain_r      = (0,0) # useful range is 0.0 to 5.65000 in steps of 0.5000
	preamp      = 0    # 0-255
	cm          = None
	playing     = None # NowPlaying instance

	def __init__(self, wire, guid):
		self.guid     = guid
		self.wire     = wire

		self.stop()
		self.mute(False, False)
		self.set_volume(200, (1,15000), (1,15000))
	
	def close(self):
		pass

	# volume manipulations

	def mute(self, analog, digital):
		aude         = Aude()
		aude.analog  = not analog  # not mute == enable
		aude.digital = not digital
		self.wire.send(aude.serialize())

	def increase_gain(self, gain, increment):
		if gain[1] + increment > 65535:
			new_gain = (gain[0] + 1, (gain[1] + increment) - 65535)
		else:
			new_gain = (gain[0], gain[1] + increment)
		if new_gain[0] > 65535:
			return (65535,65535)
		return new_gain

	def decrease_gain(self, gain, decrement):
		if gain[1] - decrement < 0:
			new_gain = (gain[0] - 1, 65535 + (gain[1] - decrement))
		else:
			new_gain = (gain[0], gain[1] - decrement)
		if new_gain[0] < 0:
			return (0,0)
		return new_gain

	def volume_up(self):
		left  = self.increase_gain(self.gain_l, 1500)
		right = self.increase_gain(self.gain_r, 1500)
		self.set_volume(self.preamp, left, right)

	def volume_down(self):
		left  = self.decrease_gain(self.gain_l, 1500)
		right = self.decrease_gain(self.gain_r, 1500)
		self.set_volume(self.preamp, left, right)

	def set_volume(self, preamp, gain_left, gain_right):
		self.preamp = preamp
		self.gain_l = gain_left
		self.gain_r = gain_right

		audg        = Audg()
		audg.dvc    = True
		audg.left   = gain_left
		audg.right  = gain_right
		audg.preamp = preamp
		self.wire.send(audg.serialize())

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

