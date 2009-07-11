# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import socket
import traceback
import sys
import os.path
import struct
import select
import time
import errno
import mutagen.mp3

from threading import Thread

from protocol import Strm, Aude, Audg

STOPPED  = 0
STARTING = 1
RUNNING  = 2

# accepts connections to a socket and then feeds data on that socket.
class Streamer(Thread):
	state   = STOPPED
	socket  = None
	port    = 0
	decoder = None # a Decoder object

	def __new__(cls, port):
		object = Thread.__new__(cls, None, Streamer.run, 'Streamer', (), {})
		return object

	def __init__(self, port):
		print('INIT streamer')
		Thread.__init__(self)
		self.state = STARTING
		self.port  = port

	def accept(self):
		if self.state != STARTING:
			print('Streamer.accept() called in wrong state %d' % self.state)
			sys.exit(1)
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Streamer waiting for port %d to become available' % self.port)
		while self.state != STOPPED: # in case someone forces a full teardown.
			try:
				self.socket.bind(('', self.port))
				break
			except:
				time.sleep(0.5)
		print('Streamer accepting on %d' % self.port)

		self.state = RUNNING

		# socket.accept() hangs and you can't abort by hitting CTRL-C on the
		# command line (because the thread isn't the program main loop that
		# receives the resulting SIGINT), so to be able to abort we set the
		# socket to time out and then try again if self.state still permits it.
		self.socket.listen(1)
		self.socket.settimeout(0.5)
		while self.state != STOPPED:
			try:
				self.socket, address = self.socket.accept()
				self.socket.setblocking(False)
				print('Streamer connected on %d' % self.port)
				break
			except:
				pass

	def run(self):
		while self.state != STOPPED:
			
			if self.state == STARTING:
				self.accept()
			
			print('Streamer listening')

			selected = [[self.socket], [self.socket], [self.socket]]
			left = 0
			while self.state == RUNNING:
				events = select.select(selected[0],selected[1],selected[2], 0.5)
				if len(events[2]) > 0:
					print('Streamer EXCEPTIONAL EVENT')
					self.state = STOPPED
					continue
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.state goes STOPPED.
					sys.stdout.write('.')
					sys.stdout.flush()
					continue

				if len(events[0]) > 0:
					sys.stdout.write('o')
					sys.stdout.flush()
					try:
						data = self.socket.recv(4096)
					except socket.error, e:
						if e[0] == errno.ECONNRESET:
							self.state = STARTING
							continue
						print('Streamer: Unhandled exception %s' % str(e))
						continue

					if data.startswith('GET /stream') and len(data) < 4096:
						self.handle_http_get(data, len(data))
						continue
					else:
						raise Exception, ( 'streamer got weird stuff to read:\n'
						                 + 'len=%d\n' % len(data)
						                 + 'data=%s\n' % data )

				if len(events[1]) > 0:
					if left == 0:
						sys.stdout.write('O')
						sys.stdout.flush()
						data = self.decoder.read()
						if data:
							left = len(data)
						else:
							left = 0
							# annoyingly, the socket is always writable when we
							# have already written everything there is to write.
							# unselect writable to avoid high CPU utilization.
							selected[1] = []
					else:
						sys.stdout.write('*')
						sys.stdout.flush()
						pass
					try:
						left = left - self.socket.send(data[-left:])
					except:
						info = sys.exc_info()
						traceback.print_tb(info[2])
						print(info[1])
						break
		print('streamer is dead')

	def feed(self, decoder):
		self.decoder = decoder

	def handle_http_get(self, data, dlen):
		# device expects an HTTP response in return. tell the decoder to send
		# the response next time it is asked for data to stream.
		if self.decoder:
			response = ( 'HTTP/1.0 200 OK\r\n'
			           + 'Content-Type: application/octet-stream\r\n'
			           + '\r\n')
			self.decoder.salt = response
		else:
			raise Exception, 'There is no decoder object to salt!'

	def stop(self):
		self.state = STOPPED

# need an extra layer of protocol handlers that use decoder objects? i.e. to
# support both files and remote streams.

class Decoder:
	salt = None
	file = None

	def open(self, path):
		self.file = open(path, 'rb')

	def read(self):
		if self.salt:
			data = self.salt
			self.salt = None
			return data
		if self.file:
			return self.file.read(4096)
		return None

	# translate time (floating point seconds) to an offset into the file and let
	# further read()'s continue from there.
	def seek(self, time):
		raise Exception, 'Your decoder must implement seek()'

class MP3_Decoder(Decoder):

	def __init__(self, path):
		self.open(path)

	def time_to_offset(self, time):
		return 0

	def seek(self, time):
		self.file.seek(self.offset, time_to_offset(time))

# playback states
STOPPED   = 0
PLAYING   = 1
PAUSED    = 2	
# buffering states
FLUSHING  = 3
BUFFERING = 4
READY     = 5
# other states
NO_STATE = -1

states_debug = {
	NO_STATE  : 'NO_STATE',
	STOPPED   : 'STOPPED',
	PLAYING   : 'PLAYING',
	PAUSED    : 'PAUSED',
	FLUSHING  : 'FLUSHING',
	BUFFERING : 'BUFFERING',
	READY     : 'READY'
}

class Player:
	playback = NO_STATE
	guid     = None # used when telling the device how to present itself
	streamer = None
	wire     = None
	gain_l   = (0,0) # 16bit.16bit expressed as uints
	gain_r   = (0,0) # useful range is 0.0 to 5.65000 in steps of 0.5000
	preamp   = 0
	
	def __init__(self, wire, guid):
		self.guid     = guid
		self.wire     = wire
		self.streamer = Streamer(port=3484)

		self.stop_playback()
		self.mute(False, False)
		self.set_volume(255, (2,25000), (2,25000))
		self.streamer.start()
	
	def close(self):
		self.streamer.stop()

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
		left  = self.increase_gain(self.gain_l, 2500)
		right = self.increase_gain(self.gain_r, 2500)
		self.set_volume(self.preamp, left, right)

	def volume_down(self):
		left  = self.decrease_gain(self.gain_l, 4000)
		right = self.decrease_gain(self.gain_r, 4000)
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

	def get_in_threshold(self, path):
		size = os.path.getsize(path)
		if size < 10*1024:
			tmp = size / 1024 # 'size' is a natural number; the result is too
			if tmp > 0:
				return tmp - 1
		return 10 # I'm just guessing
	
	def play_file(self, path):
		try:
			audio = mutagen.mp3.MP3(path)
			print(audio.info.pprint())
			self.streamer.feed(MP3_Decoder(path))
			if self.playback == PLAYING:
				self.stop_playback()
			self.start_playback(self.get_in_threshold(path))
			return True
		except:
			# presumably the path does not point to an mp3 file..
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		return False

	def flush_buffer(self):
		strm = Strm()
		strm.operation = Strm.OP_FLUSH
		self.wire.send(strm.serialize())

	def start_playback(self, in_threshold):
		if self.streamer.state != RUNNING:
			print('Streamer state %d != RUNNING' % self.streamer.state)
			return
		self.playback     = PLAYING
		strm = Strm()
		strm.operation    = Strm.OP_START
		strm.autostart    = Strm.AUTOSTART_YES
		strm.format       = Strm.FORMAT_MPEG
		strm.in_threshold = in_threshold
		strm.player_guid  = self.guid
# SqueezeCenter does this, but why? keep around if it turns out to be needed.
#			if len(strm.http_get) % 2 != 0:
#				strm.http_get = strm.http_get + '\n'
		self.wire.send(strm.serialize())

	def stop_playback(self):
		self.playback = STOPPED
		strm = Strm()
		strm.operation = Strm.OP_STOP
		self.wire.send(strm.serialize())

	def pause_playback(self):
		if self.playback == PLAYING:
			self.playback = PAUSED
			strm = Strm()
			strm.operation = Strm.OP_PAUSE
			self.wire.send(strm.serialize())
			return
		if self.playback == PAUSED:
			self.playback = PLAYING
			strm = Strm()
			strm.operation = Strm.OP_UNPAUSE
			self.wire.send(strm.serialize())
			return
		print('Player in wrong state %s to (un)pause playback!'
		     % states_debug[self.playback])
