import socket
import sys
import select
import errno
import re
import urllib

# mutagen dependency
import mutagen.mp3

from threading import Thread

STOPPED  = 0
STARTING = 1
RUNNING  = 2

class Accepting:
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
			print('Streamer.accept() called in wrong state %d' % self.state)
			sys.exit(1)
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		while self.state != STOPPED: # in case someone forces a full teardown.
			try:
				self.socket.bind(('', self.port))
				break
			except:
				self.port = self.port + 1
				pass
		print('Streamer accepting on %d' % self.port)
		
		self.state = RUNNING
		self.queue.put(Accepting('', self.port))

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
							print('Streamer connection RESET')
							self.state = STARTING
							continue
						print('Streamer: Unhandled exception %s' % str(e))
						continue

					if in_data.startswith('GET '):
						out_data = self.handle_http_get(in_data)
						out_left = len(out_data)
						if out_left > 0:
							selected[1] = [self.socket]
						continue
					else:
						raise Exception, ( 'streamer got weird stuff to read:\n'
						                 + 'len=%d\n' % len(data)
						                 + 'data=%s\n' % data )

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
							#info = sys.exc_info()
							#traceback.print_tb(info[2])
							#print(info[1])
							self.state = STARTING
							break
						continue

		print('streamer is dead')

	def handle_http_get(self, data):
		# check what resource is requested and whether to start playing it
		# at some offset:
		print data
		try:
			m = re.search('GET (.+?) HTTP/1\.0', data, re.MULTILINE)
			print 'GET %s' % m.group(1)
			track = self.backend.get_item(m.group(1))
			if track.uri.startswith('file://'):
				start = 7
			else:
				start = 0
			print 'Get %s' % urllib.unquote(track.uri[start:])
			decoder = MP3_Decoder(urllib.unquote(track.uri[start:]))
		except Exception, e:
			print 'oooops %s' % str(e)
			#info = sys.exc_info()
			#traceback.print_tb(info[2])
			#print info[1]
			# not an mp3 resource
			return 'HTTP/1.0 404 Not Found\r\n\r\n'

		try:
			m = re.search('Seek-Time: (\d+)', data, re.MULTILINE)
			decoder.seek(int(m.group(1)))
		except:
			#info = sys.exc_info()
			#traceback.print_tb(info[2])
			#print info[1]
			pass

		self.decoder = decoder

		# device expects an HTTP response in return. tell the decoder to send
		# the response next time it is asked for data to stream.
		response = 'HTTP/1.0 200 OK\r\n\r\n'
		return response + self.decoder.read(4096 - len(response))

	def stop(self):
		self.state = STOPPED

# need an extra layer of protocol handlers that use decoder objects? i.e. to
# support both files and remote streams.

class Decoder:
	file = None
	path = None

	def open(self, path):
		self.file = open(path, 'rb')
		self.path = path

	def read(self, amount=4096):
		if self.file:
			return self.file.read(amount)
		return None

	# translate time (floating point seconds) to an offset into the file and
	# let further read()'s continue from there.
	def seek(self, time):
		raise Exception, 'Your decoder must implement seek()'

class MP3_Decoder(Decoder):
	duration = 0 # float: seconds
	bitrate  = 0 # int: bits per second

	def __init__(self, path):
		audio         = mutagen.mp3.MP3(path)
		self.duration = audio.info.length
		self.bitrate  = audio.info.bitrate
		self.open(path)

	def time_to_offset(self, msec):
		return int(((self.bitrate / 1000.0) * (msec / 8.0)))

	def seek(self, msec):
		if msec > self.duration * 1000:
			print('Too large time seek value %d' % msec)
			return
		offset = self.time_to_offset(msec)
		#print('seek(%d)' % offset)
		self.file.seek(offset)

