import socket
import struct
import select
import sys
import traceback
import time

from threading import Thread
from datetime  import datetime

from tactile  import IR, TactileEvent
from protocol import ID, HeloEvent

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
			i = 0
			data = ''
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
#					if i % 10 == 0:
#						self.wire.send_stat()
					continue
				data = data + self.wire.socket.recv(1024)
				if len(data) < 8:
					print('Useless message received. length = %d' % len(data))
					break
				while len(data) >= 8:
					dlen = socket.ntohl(struct.unpack('L', data[4:8])[0])
					print '\n%s %d %d' % (data[0:4], dlen, len(data))
					self.handle(data[:8+dlen], dlen)
					data = data[8+dlen:]
		except:
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		print 'receiver is dead'

	def stop(self):
		self.alive = False

	def handle(self, data, dlen):

		if data[0:4] == 'HELO':
			if   dlen == 10:
				self.handle_helo_10(data[8:], dlen)
			elif dlen == 36:
				self.handle_helo_36(data[8:], dlen)
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

		if data[0:4] == 'RESP':
			self.handle_resp(data[8:], dlen)
			return

		print 'unknown message'
		print ['%x' % ord(c) for c in data]
		sys.exit(1)

	def handle_helo_10(self, data, dlen):
		id       = ord(data[0])
		revision = ord(data[1])

		tmp      = struct.unpack('6BH', data[2:])
		mac_addr = tuple(tmp[0:6])
		wlan_chn = socket.ntohs(tmp[6])

		# pretty silly if you ask me. why not just cook a new device number?
		if id == ID.SQUEEZEBOX2 and mac_addr[0:3] == (0x0,0x4,0x20):
			id = ID.SQUEEZEBOX3
		
		mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr
		
		print('id       : %s' % ID.debug[id])
		print('revision : %d' % revision)
		print('mac addr : %s' % mac_addr)
		print('wlan chn : %d' % wlan_chn)
		
		event = HeloEvent(id, revision, mac_addr, 1234, 'EN')
		self.queue.put(event)

	def handle_helo_36(self, data, dlen):
		id       = ord(data[0])
		revision = ord(data[1])

		tmp      = struct.unpack('6B16BHLL2s', data[2:])
		mac_addr = tuple(tmp[0:6])
		uuid     = ''.join(str(i) for i in tmp[6:22])
		wlan_chn = socket.ntohs(tmp[22])
		recv_hi  = socket.ntohl(tmp[23])
		recv_lo  = socket.ntohl(tmp[24])
		language = tmp[25]

		# pretty silly if you ask me. why not just cook a new device number?
		if id == ID.SQUEEZEBOX2 and mac_addr[0:3] == (0x0,0x4,0x20):
			id = ID.SQUEEZEBOX3
		
		mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr
		
		print('id       : %s' % ID.debug[id])
		print('revision : %d' % revision)
		print('mac addr : %s' % mac_addr)
		print('uuid     : %s' % uuid)
		print('wlan chn : %d' % wlan_chn)
		print('recv_hi  : %d' % recv_hi)
		print('recv_lo  : %d' % recv_lo)
		print('lang     : %s' % language)
		
		event = HeloEvent(id, revision, mac_addr, uuid, language)
		self.queue.put(event)

	def handle_helo_bak(self, data, len):
		id       = ord(data[0])
		revision = ord(data[1])
		mac_addr = tuple(struct.unpack('B', c)[0] for c in data[2:8])

		if revision != 2:
			uuid = struct.unpack('16B', data[8:24])
			data = data[24:]
			len  = len - 16
		else:
			uuid = [-1]
			data = data[8:]

		if len >= 10:
			wlan_chn = socket.ntohs(struct.unpack('H', data[0:2])[0])
		else:
			wlan_chn = -1

		if len >= 18:
			recv_hi = socket.ntohl(struct.unpack('L', data[2:6])[0])
			recv_lo = socket.ntohl(struct.unpack('L', data[6:10])[0])
		else:
			recv_hi = 0
			recv_lo = 0

		if len >= 20:
			language = '%s' % data[10:12]
		else:
			language = 'None'

		# pretty silly if you ask me. why not just cook a new device number?
		if id == ID.SQUEEZEBOX2 and mac_addr[0:3] == (0x0,0x4,0x20):
			id = ID.SQUEEZEBOX3

		if id not in ID.debug:
			print('Received HELO from unknown device ID %d' % id)
			return

		mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr
		uuid     = ''.join([str(i) for i in uuid])

		event = HeloEvent(id, revision, mac_addr, uuid, language)
		#print('Put %s on queue' % str(event))
		self.queue.put(event)

	def handle_bye(self, data):
		reason = struct.unpack('B', data[0])
		if reason == 1:
			print 'Player is going out for an upgrade'
		self.alive = False

	def handle_ir(self, data):
		stamp   = socket.ntohl(struct.unpack('L', data[0:4])[0])
		format  = struct.unpack('B', data[4:5])[0]
		nr_bits = struct.unpack('B', data[5:6])[0]
		code    = socket.ntohl(struct.unpack('L', data[6:10])[0])
		
		if code not in IR.codes_debug:
			print 'stamp   %d' % stamp
			print 'format  %d' % format
			print 'nr bits %d' % nr_bits
			print 'UNKNOWN ir code %d' % code
			self.last_ir = None
			#self.queue.put(TactileEvent(IR.RELEASE))
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
		event    = data[0:4]
		crlfs    = struct.unpack('B', data[4])[0]
		mas_init = struct.unpack('B', data[5])[0]
		mas_mode = struct.unpack('B', data[6])[0]
		in_size  = socket.ntohl(struct.unpack('L', data[ 7:11])[0])
		in_fill  = socket.ntohl(struct.unpack('L', data[11:15])[0])
		recv_hi  = socket.ntohl(struct.unpack('L', data[15:19])[0])
		recv_lo  = socket.ntohl(struct.unpack('L', data[19:23])[0])
		wifi_pow = socket.ntohs(struct.unpack('H', data[23:25])[0])
		jiffies  = socket.ntohl(struct.unpack('L', data[25:29])[0])
		out_size = socket.ntohl(struct.unpack('L', data[29:33])[0])
		out_fill = socket.ntohl(struct.unpack('L', data[33:37])[0])
		seconds  = socket.ntohl(struct.unpack('L', data[37:41])[0])
		voltage  = socket.ntohs(struct.unpack('H', data[41:43])[0])
		msecs    = socket.ntohl(struct.unpack('L', data[43:47])[0])
		stamp    = socket.ntohl(struct.unpack('L', data[47:51])[0])
#		error    = struct.unpack('H', data[51:53])[0]

		tail = None
		if dlen > 51:
			tail = struct.unpack('B'*(dlen-51), data[51:])

		return

		print('Event    = %s' % event)
		print('CRLFs    = %d' % crlfs)
		print('MAS init = %d' % mas_init)
		print('MAS mode = %d' % mas_mode)
		print('In buff  = %d' % in_size)
		print('In fill  = %d' % in_fill)
		print('Received = %d %d' % (recv_hi, recv_lo))
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

		if tail:
			print('Unhandled tail: %s' % str(tail))

	def handle_resp(self, data, dlen):
		# data is always an HTTP header. In fact the very same one we sent
		# on the streaming socket, unless the device is streaming from some
		# other source. simply discard the data for now.
		pass

class Wire:
	socket = None

	def __init__(self, port):
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Wire waiting for port %d to become available' % port)
		while True:
			try:
				self.socket.bind(('', port))
				break
			except:
				time.sleep(0.2) # avoid spending 99% CPU time
		print('Accepting on %d' % port)

		self.socket.listen(1)
		self.socket, address = self.socket.accept()
		print('Connected on %d' % port)

	def close(self):
#		self.socket.shutdown(socket.SHUT_RDWR)
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
	def send_audg(self, dvc, preamp, channels, legacy=None):
		print('AUDG %d %d.%d %d.%d' % (preamp, channels[0][0], channels[0][1], channels[1][0], channels[1][1]))
		cmd     = 'audg'
		if legacy:
			old     = struct.pack('LL', legacy[0],legacy[1])
		else:
			old     = struct.pack('LL', 0,0)
		new_l   = struct.pack('HH', socket.htons(channels[0][0]),
		                            socket.htons(channels[0][1]))
		new_r   = struct.pack('HH', socket.htons(channels[1][0]),
		                            socket.htons(channels[1][0]))
		dvc     = struct.pack('B',  dvc)
		preamp  = struct.pack('B',  preamp)
		payload = cmd + old + dvc + preamp + new_l + new_r
		length  = struct.pack('H', socket.htons(len(payload)))
		self.socket.send(length + payload)
