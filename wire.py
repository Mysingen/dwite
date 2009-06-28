import socket
import struct

from threading import Thread
from datetime  import datetime, timedelta

from remote import IR, RemoteEvent

class Receiver(Thread):
	connection = None
	queue      = None
	alive      = True
	last_ir    = (-1, datetime.now(), 0) # IR code, wallclock time, stress

	def __new__(cls, wire, queue):
		object = super(Receiver, cls).__new__(
			cls, None, Receiver.run, 'Receiver', (), {})
		Receiver.__init__(object, wire, queue)
		return object

	def __init__(self, wire, queue):
		Thread.__init__(self)
		self.wire  = wire
		self.queue = queue

	def run(self):
		print('Listening')
		try:
			while self.alive:
				data = self.wire.connection.recv(1024)
				dlen = struct.unpack('L', data[4:8])
				dlen = socket.ntohl(dlen[0])
#				print '\n%s %d %d' % (data[0:4], dlen, len(data))
				self.handle(data, dlen)
		except Exception, msg:
			print msg
		print 'Deaf & Dead'

	def stop(self):
		self.alive = False

	def handle(self, data, dlen):
		if data[0:4] == 'HELO':
			self.handle_helo(data[8:], dlen)
			return

		if data[0:4] == 'ANIC':
			return

		if data[0:4] == 'IR  ':
			self.handle_ir(data[8:])
			return

		if data[0:4] == 'BYE!':
			self.handle_bye(data[8:])
			return

		print 'unknown message'
		print ['%x' % ord(c) for c in data]

	def handle_helo(self, data, len):
		id       = ord(data[0])
		revision = ord(data[1])
		mac_addr = tuple(struct.unpack('B', c)[0] for c in data[2:8])

		if revision != 2:
			uuid = '%s' % struct.unpack('B', data[8:24])
			data = data[24:]
			len  = len - 16
		else:
			uuid = '-1'
			data = data[8:]

		if len >= 10:
			wlan_chn = struct.unpack('H', data[0:2])[0]
		else:
			wlan_chn = -1

		if len >= 18:
			byt_recv = struct.unpack('Q', data[2:10])[0]
		else:
			byt_recv = -1
	
		if len >= 20:
			language = '%s' % data[10:12]
		else:
			language = 'None'
		
		device_ids = {
			2:'SqueezeBox',
			3:'SoftSqueeze',
			4:'SqueezeBox 2',
			5:'Transporter',
			6:'SoftSqueeze 3',
			7:'Receiver',
			8:'SqueezeSlave',
			9:'Controller'
		}
		
		if id in device_ids:
			print 'ID       %s' % device_ids[id]
		else:
			print 'ID       %d undefined' % id
	
		print 'Revision     %d' % revision
		print 'MAC address  %2x:%2x:%2x:%2x:%2x:%2x' % mac_addr
		print 'uuid         %s' % uuid
		print 'WLAN channel %s' % wlan_chn
		print 'Bytes RX     %s' % byt_recv
		print 'Language     %s' % language

	def handle_bye(self, data):
		reason = struct.unpack('B', data[0])
		if reason == 1:
			print 'Player is going out for an upgrade'
		self.alive = False

	def handle_ir(self, data):
		stamp   = struct.unpack('L', data[0:4])[0]
		format  = struct.unpack('B', data[4:5])[0]
		nr_bits = struct.unpack('B', data[5:6])[0]
		code    = struct.unpack('L', data[6:10])[0]
		
		ir_codes_debug = {
			IR.SLEEP      :'SLEEP',
			IR.POWER      :'POWER',
			IR.HARD_POWER :'HARD POWER DOWN?',
			IR.REWIND     :'REWIND',
			IR.PAUSE      :'PAUSE',
			IR.FORWARD    :'FORWARD',
			IR.ADD        :'ADD',
			IR.PLAY       :'PLAY',
			IR.UP         :'UP',
			IR.LEFT       :'LEFT',
			IR.RIGHT      :'RIGHT',
			IR.DOWN       :'DOWN',
			IR.VOLUME_DOWN:'VOLUME-',
			IR.VOLUME_UP  :'VOLUME+',
			IR.NUM_0      :'0',
			IR.NUM_1      :'1',
			IR.NUM_2      :'2',
			IR.NUM_3      :'3',
			IR.NUM_4      :'4',
			IR.NUM_5      :'5',
			IR.NUM_6      :'6',
			IR.NUM_7      :'7',
			IR.NUM_8      :'8',
			IR.NUM_9      :'9',
			IR.FAVORITES  :'FAVORITES',
			IR.SEARCH     :'SEARCH',
			IR.BROWSE     :'BROWSE',
			IR.SHUFFLE    :'SHUFFLE',
			IR.REPEAT     :'REPEAT',
			IR.NOW_PLAYING:'NOW PLAYING',
			IR.SIZE       :'SIZE',
			IR.BRIGHTNESS :'BRIGHTNESS'
		}

#		print 'stamp   %d' % stamp
#		print 'format  %d' % format
#		print 'nr bits %d' % nr_bits
		if code in ir_codes_debug:
#			print 'ir code %s' % ir_codes_debug[code]
			pass
		else:
			print 'UNKNOWN ir code %d' % code
			return

		now    = datetime.now()
		stress = 1
		if self.last_ir[0] == code:
			delta = now - self.last_ir[1]
			# if delta is less than 0.1 seconds, then the key is kept pressed.
			if (delta.days == 0
			and delta.seconds == 0
			and delta.microseconds < 100000):
#				print 'delta   %s' % str(delta)
				stress = self.last_ir[2] + 1
		self.last_ir = (code, now, stress)

		# accelerate the frequency of events as the user keeps a key pressed for
		# longer times. if stress is past some particular level and a multiple of
		# something specific to that level, then send an event.
		acceleration = [ 1,  8, 15, 22, 29, 36, 43,
		                48, 53, 58, 63, 68, 73, 78,
		                81, 84, 87, 91, 94, 97, 100]
		
		if stress in acceleration or stress > 100:
			self.queue.put(RemoteEvent(code, stress))

class Wire:
	connection = None

	def __init__(self, port):
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Waiting for port %d to become available. No timeout' % port)
		while 1:
			try:
				sock.bind(('', port))
				break
			except socket.error, msg:
				pass
		print('Accepting')

		sock.listen(1)
		self.connection, address = sock.accept()
		print('Connected')

	def close(self):
		self.connection.close() # this will cause self.listener to terminate

	def send_grfe(self, bitmap, transition):
		cmd      = 'grfe'
		offset   = struct.pack('H', socket.htons(0)) # must be zero. why?
		distance = struct.pack('B', 32) # 32 is Y-axis. not properly understood
		payload  = cmd + offset + transition + distance + bitmap
		length   = socket.htons(len(payload))
		length   = struct.pack('H', length)
		self.connection.send(length + payload)

	def send_grfb(self, brightness):
		cmd      = 'grfb'
		payload  = cmd + struct.pack('H', socket.htons(brightness))
		length   = socket.htons(len(payload))
		length   = struct.pack('H', length)
		self.connection.send(length + payload)