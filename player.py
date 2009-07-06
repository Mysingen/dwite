import socket
import traceback
import sys
import os.path
import struct
import select

from threading import Thread

from mutagen.mp3 import MP3

#from wire import Streamer

# accepts connections to a socket and then feeds data on that socket.
class Streamer(Thread):
	socket  = None
	decoder = None # a Decoder object
	alive   = True
	port    = 0    # listening port

	def __new__(cls, port):
		object = Thread.__new__(cls, None, Streamer.run, 'Streamer', (), {})
		Streamer.__init__(object, port)
		return object

	def __init__(self, port):
		Thread.__init__(self)
		self.port = port

	def accept(self):
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Waiting for port %d to become available. No timeout' % self.port)
		while self.alive:
			try:
				self.socket.bind(('', self.port))
				break
			except socket.error, msg:
				pass
		print('Accepting on %d' % self.port)

		self.socket.listen(1)
		self.socket.settimeout(0.1)
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
			events = select.select([self.socket],[self.socket],[self.socket], 0.1)
			if len(events[2]) > 0:
				print('wire EXCEPTIONAL EVENT')
				break
			if events == ([],[],[]):
				continue
			if len(events[0]) > 0:
				data = self.socket.recv(1024)
				print data
				continue
			if len(events[1]) > 0:
				if left == 0:
					data = self.decoder.read()
					left = len(data)
				try:
					left = left - self.socket.send(data)
				except:
					info = sys.exc_info()
					traceback.print_tb(info[2])
					print(info[1])
					pass # try again. if the user gives up, 'alive' will go False.
		print('streamer is dead')

	def stop(self):
		self.alive = False

class StreamCommand:
	command   = '?' # 's'tart, 'p'ause, 'u'npause, 'q'uit, 'f'lush
	autostart = '?' # '0'=no, '1'=yes, '2'=extern no, '3'=extern yes
	                # ("extern" as in "extern source". e.g. internet radio.)
	format    = '?' # 'm'peg, 'p'cm, 'p'=wav/aif, 'f'lc, 'w'ma/asx, 'o'gg

	pcm_sample_size = '?' # '0'=8, '1'=16, '2'=24, '3'=32
	pcm_sample_rate = '?' # '0'=11, '1'=22, '2'=32, '3'=44.1, '4'=48,
	                      # '5'=8,  '6'=12, '7'=16, '8'=24,   '9'=96 (KHz)
	pcm_channels    = '?' # '1'=mono, '2'=stereo
	pcm_endianness  = '?' #	'0'=big, '1'=little

	in_threshold = struct.pack('B', 10) # KBytes of input data to buffer before
	                    # autostarting and/or notifying the server of buffer
	                    # status
	spdif        = struct.pack('B', 1) # 0=auto, 1=enable, 2=disable
	fade_time    = struct.pack('B', 0) # seconds to spend on fading between songs
	fade_type    = '0'  # '0'=none, '1'=cross, '2'=in, '3'=out, '4'=in&out
	flags        = struct.pack('B', 0) # uint8:
	                    # 0x80=loop forever
	                    # 0x40=don't restart the decoder (when do you?)
	                    # 0x02=invert polarity (right)
	                    # 0x01=invert polarity (left)
	out_threshold = struct.pack('B', 1) # 0.1 seconds of decoded audio to buffer
	                    # before starting playback.
	reserved      = struct.pack('B', 0)
	gain          = struct.pack('HH', 0, 0) # playback gain in 16.16 fixed point
	                    # fixed point. 0=none
	server_port   = struct.pack('H', socket.htons(3484)) # where to get the data
	                    # stream (server port number)
	server_ip     = struct.pack('L', socket.htons(0)) # where to get the data
	                    # stream (server address). zero makes it use the same
	                    # as the control server
	http_get      = 'GET /stream.mp3?player=%s HTTP/1.0\n'

	def serialize(self):
		tmp = (self.command
		      + self.autostart
		      + self.format
		      + self.pcm_sample_size
		      + self.pcm_sample_rate
		      + self.pcm_channels
		      + self.pcm_endianness
		      + self.in_threshold
		      + self.spdif
		      + self.fade_time
		      + self.fade_type
		      + self.flags
		      + self.out_threshold
		      + self.reserved
		      + self.gain
		      + self.server_port
		      + self.server_ip)
		if len(tmp) != 24:
			raise Exception, 'strm command not 24 bytes in lenght'
		return tmp

# need an extra layer of protocol handlers that use decoder objects? i.e. to
# support both files and remote streams.

class Decoder:
	file = None

	def open(self, path):
		self.file = open(path, 'rb')

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

	def read(self):
		return self.file.read(4096)

class Player:
	streamer = None
	wire     = None
	volume_l = (0,0) # 16bit.16bit expressed as uints
	volume_r = (0,0) # useful range is 0.0 to 5.65000 in steps of 0.5000
	
	def __init__(self, wire):
		self.wire     = wire
		self.streamer = Streamer(port=3484)
		self.streamer.start()
		self.mute(False, False)
	
	def close(self):
		self.streamer.stop()

	def mute(self, analog, digital):
		self.wire.send_aude(not analog, not digital) # not mute == enable

	def increase_volume(self, channel, increment):
		if channel[1] + increment > 65535:
			return (channel[0] + 1, (channel[1] + increment) - 65535)
		return (channel[0], channel[1] + increment)

	def decrease_volume(self, channel, decrement):
		if channel[1] - decrement < 0:
			return (channel[0] - 1, 65535 + (channel[1] - decrement))
		return (channel[0], channel[1] - decrement)

	def volume_up(self):
		l = self.increase_volume(self.volume_l, 2500)
		r = self.increase_volume(self.volume_r, 2500)
		if l[0] > 5 or r[0] > 5:
			return
		self.volume_l = l
		self.volume_r = r
		self.wire.send_audg(True, 0, (self.volume_l, self.volume_r))

	def volume_down(self):
		l = self.decrease_volume(self.volume_l, 4000)
		r = self.decrease_volume(self.volume_r, 4000)
		if l[0] < 0 or r[0] < 0:
			l = (0,0)
			r = (0,0)
		self.volume_l = l
		self.volume_r = r
		self.wire.send_audg(True, 0, (self.volume_l, self.volume_r))
	
	def get_in_threshold(self, path):
		size = os.path.getsize(path)
		if size < 10*1024:
			tmp = size / 1024 # size is a natural number, so the result is too
			if tmp > 0:
				return tmp - 1
		return 10 # I'm just guessing
	
	def play_file(self, path):
		try:
			audio = MP3(path)
			print(audio.info.pprint())
			self.streamer.feed(MP3_Decoder(path))
			strm = StreamCommand()
			strm.command      = 's'
			strm.autostart    = '1'
			strm.format       = 'm'
			strm.in_threshold = struct.pack('B', self.get_in_threshold(path))
			strm.http_get = 'GET /stream.mp3?player=%s HTTP/1.0\n' % '00:19:e3:07:e5:cb'
			if len(strm.http_get) % 2 != 0:
				strm.http_get = strm.http_get + '\n' # SqueezeCenter does, but why?
			self.wire.send_strm(strm.serialize())
			return True
		except:
			# presumably the path does not point to an mp3 file..
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		return False
