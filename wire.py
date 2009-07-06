import socket
import struct
import select
import sys
import traceback
import time

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
				#print '\n%s %d %d' % (data[0:4], dlen, len(data))
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
		
		if data[0:4] == 'STAT':
			self.handle_stat(data[8:], dlen)
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

	def handle_stat(self, data, dlen):
		return
		print('len = %d/%d' % (dlen, len(data)))

		event    = data[0:4]
		crlfs    = struct.unpack('B', data[4])[0]
		mas_init = data[5]
		mas_mode = struct.unpack('B', data[6:7])[0]
		in_size  = struct.unpack('L', data[7:11])[0]
		in_fill  = struct.unpack('L', data[11:15])[0]
		received = struct.unpack('Q', data[15:23])[0]
		wifi_pow = struct.unpack('H', data[23:25])[0]
		jiffies  = struct.unpack('L', data[25:29])[0]
		out_size = struct.unpack('L', data[29:33])[0]
		out_fill = struct.unpack('L', data[33:37])[0]
		seconds  = struct.unpack('L', data[37:41])[0]
		voltage  = struct.unpack('H', data[41:43])[0]
		msecs    = struct.unpack('L', data[43:47])[0]
		stamp    = struct.unpack('L', data[47:51])[0]

#		error    = struct.unpack('H', data[51:53])[0]
		
		print('Event    = %s' % event)
		print('CRLFs    = %d' % crlfs)
		print('MAS init = %c' % mas_init)
		print('MAS mode = %d' % mas_mode)
		print('In buff  = %d' % in_size)
		print('In fill  = %d' % in_fill)
		print('Received = %d' % received)
		if wifi_pow <= 100:
			print('WiFi pow = %d' % wifi_pow)
		else:
			print('Connection = Wired')
		print('Jiffies  = %d' % jiffies)
		print('Out buff = %d' % out_size)
		print('Out fill = %d' % out_fill)
		print('Elapsed  = %d.%d' % (seconds, msecs))
		print('Voltage  = %d' % voltage)
		print('Stamp    = %d' % stamp)
#		print('Error    = %d' % error)
		

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
				time.sleep(0.1)
				pass
		print('Accepting on %d' % port)

		self.socket.listen(1)
		self.socket, address = self.socket.accept()
		print('Connected on %d' % port)

	def close(self):
		self.socket.shutdown(socket.SHUT_RDWR)
		self.socket.close()

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

	def send_strm(self, parameters):
		cmd     = 'strm'
		payload = cmd + parameters
		length = struct.pack('H', socket.htons(len(payload)))
		self.socket.send(length + payload)

	def send_aude(self, analog, digital):
		cmd     = 'aude'
		dac     = struct.pack('B', analog)
		spdif   = struct.pack('B', digital)
		payload = cmd + spdif + dac
		length  = struct.pack('H', socket.htons(len(payload)))
		self.socket.send(length + payload)

	# channels is a tuple of integer tuples: ((16bit,16bit), (16bit,16bit))
	# dvc (digital volume control?) is boolean
	# preamp must fit in a uint8
	def send_audg(self, dvc, preamp, channels):
		cmd     = 'audg'
		old     = struct.pack('LL', 0, 0)
		new_l   = struct.pack('HH', socket.htons(channels[0][0]),
		                            socket.htons(channels[0][1]))
		new_r   = struct.pack('HH', socket.htons(channels[1][0]),
		                            socket.htons(channels[1][0]))
		dvc     = struct.pack('B',  dvc)
		preamp  = struct.pack('B',  preamp)
		payload = cmd + old + dvc + preamp + new_l + new_r
		length  = struct.pack('H', socket.htons(len(payload)))
		self.socket.send(length + payload)
