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
import mutagen.mp3

from threading import Thread

from protocol import Strm

STOPPED   = 0
STREAMING = 1

# accepts connections to a socket and then feeds data on that socket.
class Streamer(Thread):
	socket  = None
	decoder = None # a Decoder object
	alive   = True
	state   = STOPPED
	port    = 0    # listening port

	def __new__(cls, port):
		object = super(Thread, cls).__new__(
			cls, None, Streamer.run, 'Streamer', (), {})
		Streamer.__init__(object, port)
		return object

	def __init__(self, port):
		Thread.__init__(self)
		self.port   = port
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

	def accept(self):
		print('Streamer waiting for port %d to become available' % self.port)
		while self.alive:
			try:
				self.socket.bind(('', self.port))
				break
			except:
				time.sleep(0.2)
		print('Accepting on %d' % self.port)

		self.socket.listen(1)
		self.socket.settimeout(0.2)
		while self.alive:
			try:
				self.socket, address = self.socket.accept()
				self.socket.setblocking(False)
				print('Connected on %d' % self.port)
				break
			except:
				pass

	def feed(self, decoder):
		self.decoder = decoder

	def run(self):
		self.accept()

		left = 0
		while self.alive:
			events = select.select(
				[self.socket],[self.socket],[self.socket], 0.1)
			if len(events[2]) > 0:
				print('streamer EXCEPTIONAL EVENT')
				break
			if events == ([],[],[]):
#				sys.stdout.write('.')
#				sys.stdout.flush()
				continue
			if len(events[0]) > 0:
#				sys.stdout.write('o')
#				sys.stdout.flush()
				data = self.socket.recv(4096)
				if data.startswith('GET /stream') and len(data) < 4096:
					self.handle_http_get(data, len(data))
					continue
				else:
					raise Exception, ( 'streamer got weird stuff to read:\n'
					                 + 'len=%d\n' % len(data)
					                 + 'data=%s\n' % data )
			if len(events[1]) > 0:
#				sys.stdout.flush()
				if self.state != STREAMING:
					print('streamer can write but isn\'t streaming!')
					time.sleep(0.1)
					continue
				if left == 0:
#					sys.stdout.write('O')
					data = self.decoder.read()
					left = len(data)
				else:
#					sys.stdout.write('*')
					pass
				try:
					left = left - self.socket.send(data[-left:])
				except:
					info = sys.exc_info()
					traceback.print_tb(info[2])
					print(info[1])
					pass # try again. if user gives up, 'alive' goes False
		print('streamer is dead')

	def handle_http_get(self, data, dlen):
		# device supposedly expects an HTTP response
		if self.decoder:
			response = ( 'HTTP/1.0 200 OK\r\n'
			           + 'Content-Type: application/octet-stream\r\n'
			           + '\r\n')
			self.decoder.salt(response)
			self.state = STREAMING
		else:
			raise Exception, 'There is no decoder object to salt!'

	def stop(self):
		self.alive = False

# need an extra layer of protocol handlers that use decoder objects? i.e. to
# support both files and remote streams.

class Decoder:
	salt = None
	file = None

	def open(self, path):
		self.file = open(path, 'rb')

	def salt(self, data):
		self.salt = data

	def read(self):
		if self.salt:
			data = self.salt
			self.salt = None
			return data
		if self.file:
			return self.file.read(4096)
		return ''

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

class Player:
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

	def mute(self, analog, digital):
		self.wire.send_aude(not analog, not digital) # not mute == enable

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
		self.wire.send_audg(True, preamp, (gain_left, gain_right))

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
			strm = Strm()
			strm.operation    = Strm.OP_START
			strm.autostart    = Strm.AUTOSTART_YES
			strm.format       = Strm.FORMAT_MPEG
			strm.in_threshold = self.get_in_threshold(path)
			strm.player_guid  = self.guid
# SqueezeCenter does this, but why? keep around if it turns out to be needed.
#			if len(strm.http_get) % 2 != 0:
#				strm.http_get = strm.http_get + '\n'
			print('send_strm')
			self.wire.send(strm.serialize())
			return True
		except:
			# presumably the path does not point to an mp3 file..
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		return False

	def stop_playback(self):
		strm = Strm()
		strm.operation = Strm.OP_STOP
		self.wire.send(strm.serialize())
