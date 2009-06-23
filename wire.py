import socket
import struct

from threading import Thread

from remote import IR, Remote

class Receiver(Thread):
	connection = None
	queue      = None

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
			while 1:
				data = self.wire.connection.recv(1024)
				dlen = struct.unpack('L', data[4:8])
				dlen = socket.ntohl(dlen[0])
				print '\n%s %d %d' % (data[0:4], dlen, len(data))
				self.handle(data, dlen)
		except Exception, msg:
			print msg
			return

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

	def handle_ir(self, data):
		time    = struct.unpack('L', data[0:4])[0]
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

		print 'time    %d' % time
		print 'format  %d' % format
		print 'nr bits %d' % nr_bits
		if code in ir_codes_debug:
			print 'ir code %s' % ir_codes_debug[code]
		else:
			print 'UNKNOWN ir code %d' % code
			return

		self.queue.put(Remote(code))

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
