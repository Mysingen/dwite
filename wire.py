import socket
import struct

from threading import Thread

class Listener(Thread):
	connection = None
	reactor    = None

	def __new__(cls, connection, reactor):
		object = super(Listener, cls).__new__(
			cls, None, Listener.run, 'Listener', (), {})
		Listener.__init__(object, connection, reactor)
		return object

	def __init__(self, connection, reactor):
		Thread.__init__(self)
		self.connection = connection
		self.reactor    = reactor

	def run(self):
		try:
			while 1:
				data = self.connection.recv(1024)
				dlen = struct.unpack('L', data[4:8])
				dlen = socket.ntohl(dlen[0])
				print '\n%s %d %d' % (data[0:4], dlen, len(data))
				self.reactor.handle(data, dlen)
		except Exception, msg:
			print msg
			return

# this class knows the full protocol that a SqueezeBox may use in transmissions
# to the host. the name "prototocol" is avoided because it only implements the
# part that reacts to what the other party is sending. other classes implement
# protocol "actors".
class Reactor:
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

		if id in self.device_ids:
			print 'ID       %s' % self.device_ids[id]
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

	ir_codes = {
		1203276150:'SLEEP',
		3208677750:'POWER',
		16187392  :'HARD POWER DOWN?',
		1069582710:'REWIND',
		3743451510:'PAUSE',
		1604356470:'FORWARD',
		2673903990:'ADD',
		4010838390:'PLAY',
		534808950 :'UP',
		1871743350:'LEFT',
		802195830 :'RIGHT',
		1336969590:'DOWN',
		4278225270:'VOLUME-',
		2139130230:'VOLUME+',
		267422070 :'1',
		4144531830:'2',
		2005436790:'3',
		3074984310:'4',
		935889270 :'5',
		3609758070:'6',
		1470663030:'7',
		2540210550:'8',
		401115510 :'9',
		1738049910:'0',
		3877144950:'FAVORITES',
		# SEARCH button not reactive in emulator
		2406517110:'BROWSE',
		668502390 :'SHUFFLE',
		3342371190:'REPEAT',
		2272823670:'NOW PLAYING',
		133728630 :'SIZE',
		4211378550:'BRIGHTNESS'
	}

	def handle_ir(self, data):
		time    = struct.unpack('L', data[0:4])[0]
		format  = struct.unpack('B', data[4:5])[0]
		nr_bits = struct.unpack('B', data[5:6])[0]
		code    = struct.unpack('L', data[6:10])[0]
		
		print 'time    %d' % time
		print 'format  %d' % format
		print 'nr bits %d' % nr_bits
		if code in self.ir_codes:
			print 'ir code %s' % self.ir_codes[code]
		else:
			print 'ir code %d' % code



class Wire:
	host       = ''
	port       = 0
	sock       = None
	connection = None
	address    = None
	listener   = None
	reactor    = None

	def __init__(self, port):
		self.port = port
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Waiting for port %d to become available. No timeout' % self.port)
		while 1:
			try:
				self.sock.bind((self.host, self.port))
				break
			except socket.error, msg:
				pass
		print('Accepting')

		self.sock.listen(1)
		self.connection, self.address = self.sock.accept()
		print('Connected')

		self.reactor  = Reactor()
		self.listener = Listener(self.connection, self.reactor)
		self.listener.start()
		print('Listening')

	def close(self):
		self.connection.close() # this will cause self.listener to terminate
