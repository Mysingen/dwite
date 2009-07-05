import socket
import struct
import select
import sys
import traceback

from threading import Thread
from datetime  import datetime

from tactile import IR, TactileEvent

class Receiver(Thread):
	wire    = None
	queue   = None
	alive   = True
	last_ir = None # tuple: (IR code, wallclock time, stress)

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
				sock = self.wire.socket
				events = select.select([sock],[],[sock], 0.1)
				if len(events[2]) > 0:
					#print('wire EXCEPTIONAL EVENT')
					break
				if events == ([],[],[]):
					# a lack of events is treated as if the user released a button
					if self.last_ir != None:
						self.last_ir = None
						self.queue.put(TactileEvent(IR.RELEASE))
					continue
				data = self.wire.socket.recv(1024)
				if len(data) < 8:
					#print('Useless message received. length = %d' % len(data))
					break
				dlen = struct.unpack('L', data[4:8])
				dlen = socket.ntohl(dlen[0])
#				print '\n%s %d %d' % (data[0:4], dlen, len(data))
				self.handle(data, dlen)
		except:
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		print 'wire is Deaf & Dead'

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
		
		if code not in IR.codes_debug:
			print 'stamp   %d' % stamp
			print 'format  %d' % format
			print 'nr bits %d' % nr_bits
			print 'UNKNOWN ir code %d' % code
			self.last_ir = None
			self.queue.put(TactileEvent(IR.RELEASE))
			return

		now = datetime.now()
		stress = 0
		if self.last_ir and self.last_ir[0] == code:
			# the same key is kept pressed. don't send a new event.
			stress = self.last_ir[2] + 1
			#print('wire stress %s %d' % (IR.codes_debug[code], stress))
		else:
			#print('wire put %s' % IR.codes_debug[code])
			self.queue.put(TactileEvent(code))
		# either way track what happened.
		self.last_ir = (code, now, stress)

class Wire:
	socket = None

	def __init__(self, port):
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Waiting for port %d to become available. No timeout' % port)
		while 1:
			try:
				self.socket.bind(('', port))
				break
			except socket.error, msg:
				pass
		print('Accepting')

		self.socket.listen(1)
		self.socket, address = self.socket.accept()
		print('Connected')

	def send_grfe(self, bitmap, transition):
		cmd      = 'grfe'
		offset   = struct.pack('H', socket.htons(0)) # must be zero. why?
		distance = struct.pack('B', 32) # 32 is Y-axis. not properly understood
		payload  = cmd + offset + transition + distance + bitmap
		length   = socket.htons(len(payload))
		length   = struct.pack('H', length)
		self.socket.send(length + payload)

	def send_grfb(self, brightness):
		cmd      = 'grfb'
		payload  = cmd + struct.pack('H', socket.htons(brightness))
		length   = socket.htons(len(payload))
		length   = struct.pack('H', length)
		self.socket.send(length + payload)
