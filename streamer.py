# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import socket
import select
import errno
import re
import urllib
import os
import flac.decoder
import traceback

# mutagen dependency
import mutagen

from threading import Thread

STOPPED  = 0
STARTING = 1
RUNNING  = 2

class Accepting(object):
	host = None
	port = 0

	def __init__(self, host, port):
		self.host = host
		self.port = port

# accepts connections to a socket and then feeds data on that socket.
class Streamer(Thread):
	state   = STOPPED
	socket  = None
	port    = 0
	decoder = None # a Decoder object
	backend = None

	def __init__(self, backend, queue):
		Thread.__init__(self, target=Streamer.run, name='Streamer')
		self.state   = STARTING
		self.port    = 3485
		self.backend = backend
		self.queue   = queue

	def accept(self):
		if self.state != STARTING:
			raise Excepion(
				'Streamer.accept() called in wrong state %d' % self.state
			)
		if self.socket:
			try:
				#self.socket.flush()
				self.socket.shutdown(socket.SHUT_RDWR)
			except Exception, e:
				if type(e) == socket.error and e[0] == errno.ENOTCONN:
					pass
				else:
					print('INTERNAL ERROR')
					traceback.print_exc()
					self.stop()
					return
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		while self.state != STOPPED: # in case someone forces a full teardown.
			try:
				self.socket.bind(('', self.port))
				break
			except:
				self.port = self.port + 1
				pass
		#print('Streamer accepting on %d' % self.port)
		
		self.state = RUNNING
		self.queue.put(Accepting('', self.port))

		# socket.accept() hangs and you can't abort by hitting CTRL-C on the
		# command line (because the thread isn't the program main loop that
		# receives the resulting SIGINT), so to be able to abort we set the
		# socket to time out and then try again if self.state still permits it.
		self.socket.listen(0)
		self.socket.settimeout(0.5)
		while self.state != STOPPED:
			try:
				self.socket, address = self.socket.accept()
				self.socket.setblocking(False)
				#print('Streamer connected on %d' % self.port)
				break
			except:
				pass

	def run(self):
		while self.state != STOPPED:
			
			if self.state == STARTING:
				self.accept()

			selected = [[self.socket], [], [self.socket]]
			out_data = None
			out_left = 0
			while self.state == RUNNING:
				events = select.select(selected[0],selected[1],selected[2],0.5)
				if len(events[2]) > 0:
					print('Streamer EXCEPTIONAL EVENT')
					self.state = STOPPED
					continue
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.state goes STOPPED.
					continue

				if len(events[0]) > 0:
					try:
						in_data = self.socket.recv(4096)
					except socket.error, e:
						if e[0] == errno.ECONNRESET:
							#print('Streamer connection RESET')
							self.state = STARTING
							continue
					except Exception, e:
						print('INTERNAL ERROR')
						traceback.print_exc()
						self.stop()

					if len(in_data) == 0:
						continue

					if in_data.startswith('GET '):
						out_data = self.handle_http_get(in_data.decode('utf-8'))
						out_left = len(out_data)
						if out_left > 0:
							selected[1] = [self.socket]
						continue
					else:
						raise Exception, ( 'streamer got weird stuff to read:\n'
						                 + 'len=%d\n' % len(in_data)
						                 + 'data=%s\n' % in_data )

				if len(events[1]) > 0:
					if out_left == 0:
						out_data = None
						if self.decoder:
							out_data = self.decoder.read()
						if out_data:
							out_left = len(out_data)
						else:
							out_left = 0
							# annoyingly, the socket is always writable when we
							# have already written everything there is to write.
							# unselect writable to avoid high CPU utilization.
							selected[1] = []
							continue

					else:
						try:
							sent = self.socket.send(out_data[-out_left:])
							out_left = out_left - sent
						except:
							print('INTERNAL ERROR')
							traceback.print_exc()
							self.stop()
						continue

		#print('streamer is dead')

	def handle_http_get(self, data):
		# check what resource is requested and whether to start playing it
		# at some offset:
		print data.strip()
		try:
			m = re.search('GET (.+?)\?seek=(\d+) HTTP/1\.0', data, re.MULTILINE)
			track = self.backend.get_item(m.group(1))
			seek  = m.group(2)
			if track.uri.startswith('file://'):
				path = track.uri[7:]
			else:
				path = track.uri
			path = urllib.unquote(path)
			# if path is the same as for previous request, then the user is
			# seeking in the file and we can keep the old decoder. otherwise
			# create a new one:
			if (not self.decoder) or (self.decoder.path != path):
				try:
					self.decoder = Decoder(path)
				except:
					return 'HTTP/1.0 404 Not Found\r\n\r\n'
					
		except Exception, e:
			traceback.print_exc()
			return 'HTTP/1.0 404 Not Found\r\n\r\n'

		try:
			self.decoder.seek(int(seek))
		except Exception, e:
			traceback.print_exc()

		# device expects an HTTP response in return. tell the decoder to send
		# the response next time it is asked for data to stream.
		response = ( 'HTTP/1.0 200 OK\r\n'
		           + 'Content-Type: %s\r\n' % self.decoder.mimetype
		           + '\r\n\r\n' )
		return response

	def stop(self):
		self.state = STOPPED

# need an extra layer of protocol handlers that use decoder objects? i.e. to
# support both files and remote streams.

class Decoder:
	path     = None
	file     = None
	audio    = None
	frames   = None # FLAC (and other formats) must be streamed frame-aligned.
	                # create the list of aligned offsets as needed.
	mimetype = None

	def __init__(self, path):
		self.path = path
		if not os.path.exists(path):
			# filenames with characters of unknown encoding can still be found
			# this way because the CM is supposed to handle non-UTF8 filenames
			# by replacing the weird characters with escape representations.
			# try to un-escape such characters and check for the file again.
			# if it still can't be found, then it really doesn't exist. note
			# that we still set Decoder.path to the path that couldn't be found
			# as it should be the path passed from the DM.
			path = path.decode('string_escape')
		if not os.path.exists(path):
			raise Exception('No such file')
		self.audio = mutagen.File(path, easy=True)
		self.file = open(path, 'rb')
		if type(self.audio) == mutagen.mp3.EasyMP3:
			self.mimetype = 'audio/mpeg'
		elif type(self.audio) == mutagen.flac.FLAC:
			self.mimetype = 'audio/flac'

	def read(self, amount=65536):
		if self.file:
			return self.file.read(amount)
		return None

	def time_to_offset(self, msec):
		if type(self.audio) == mutagen.mp3.EasyMP3:
			if msec == 0:
				return 0
			# bits per msec: bitrate / 1000
			# bytes per msec: bits per msec / 8
			# offset: bytes per msec * time
			return (self.audio.info.bitrate * msec) / 8000
		if type(self.audio) == mutagen.flac.FLAC:
			# find an aligned byte offset by picking the .frames[] index that
			# most closely matches the seek value.
			def make_frames():
				if self.frames:
					return
				def metadata_cb(decoder, block):
					pass
				def error_cb(decoder, status):
					raise Exception('error_cb()')
				def write_cb(decoder, buff, size):
					pass
				self.frames = []
				dec = flac.decoder.StreamDecoder()
				# path parameter must not be unicode:
				dec.init(
					self.path.encode('utf-8'), write_cb, metadata_cb, error_cb
				)
				dec.process_until_end_of_metadata()
				while dec.get_state() != 4:
					self.frames.append(dec.get_decode_position())
					dec.skip_single_frame()
			try:
				make_frames()
			except Exception, e:
				traceback.print_exc()
				
			duration = self.audio.info.length * 1000
			index = int((msec / duration) * len(self.frames))
			if msec <= duration:
				result = self.frames[index]
			else:
				result = self.frames[-1]
			#print(
			#	'flac seek %d of %d msec = %d byte offset (of %d)'
			#	% (msec, int(duration), result, os.path.getsize(self.path))
			#)
			return result

		raise Exception('Unhandled execution path')

	# translate time to an offset into the file and let further read()'s
	# continue from there.
	def seek(self, msec):
		if msec > int(self.audio.info.length * 1000):
			print('Too large time seek value %d' % msec)
			return
		self.file.seek(self.time_to_offset(msec))

