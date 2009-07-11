# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import struct
import socket

from tactile import IR

class ID:
	SQUEEZEBOX   = 2
	SOFTSQUEEZE  = 3
	SQUEEZEBOX2  = 4
	TRANSPORTER  = 5
	SOFTSQUEEZE3 = 6
	RECEIVER     = 7
	SQUEEZESLAVE = 8
	CONTROLLER   = 9
	SQUEEZEBOX3  = 104 # not reported by firmware, but infered from HELO msg.

	debug = {
		SQUEEZEBOX   : 'SqueezeBox',
		SOFTSQUEEZE  : 'SoftSqueeze',
		SQUEEZEBOX2  : 'SqueezeBox_2',
		TRANSPORTER  : 'Transporter',
		SOFTSQUEEZE3 : 'SoftSqueeze_3',
		RECEIVER     : 'Receiver',
		SQUEEZESLAVE : 'SqueezeSlave',
		CONTROLLER   : 'Controller',
		SQUEEZEBOX3  : 'SqueezeBox_3'
	}

# there are Messages and Commands. Messages are inbound from the device and
# Commands are outbound to the device. The parser produces Message instances
# while the Command base class has a virtual function serialize() that all
# subclasses must implement. The serialized representation shall be writable
# on the control connection's socket.

class Message:
	head = None # string

class Helo(Message):
	head = 'HELO'

	def __init__(self, id, revision, mac_addr, uuid, language):
		self.id       = id       # integer
		self.revision = revision # integer
		self.mac_addr = mac_addr # string
		self.uuid     = uuid     # string
		self.language = language # string

	def __str__(self):
		return 'HELO: %s %d %s %s %s' % (ID.debug[self.id], self.revision,
		                           self.mac_addr, self.uuid, self.language)

class Anic(Message):
	head = 'ANIC'

	def __str__(self):
		return 'ANIC: -'

class Tactile(Message):
	head   = 'IR  '
	code   = 0 # valid values taken from tactile.IR
	stress = 0 # integer

	def __init__(self, code, stress=0):
		self.code   = code
		self.stress = stress

	def __str__(self):
		return 'IR  : %s %d' % (IR.codes_debug[self.code], self.stress)

class Bye(Message):
	head   = 'BYE '
	reason = 0 # integer

	def __init__(self, reason):
		self.reason = reason
	
	def __str__(self):
		if reason == 1:
			return 'BYE : Player is going out for an upgrade'
		return 'BYE : %d' % self.reason

class Stat(Message):
	head     = 'STAT'
	event    = None # 4 byte string
	crlfs    = 0    # uint8
	mas_init = 0    # uint8
	mas_mode = 0    # uint8
	in_size  = 0    # uint32
	in_fill  = 0    # uint32
	recv_hi  = 0    # uint32
	recv_lo  = 0    # uint32
	wifi_pow = 0    # uint16
	jiffies  = 0    # uint32
	out_size = 0    # uint32
	out_fill = 0    # uint32
	seconds  = 0    # uint32
	voltage  = 0    # uint32
	msecs    = 0    # uint32
	stamp    = 0    # uint32
	error    = 0    # uint16 (only set in STAT/STMn?)

	def __str__(self):
		return 'HEAD %s' % self.event

		tmp1 = ( 'Event    = %s\n' % self.event
		       + 'CRLFs    = %d\n' % self.crlfs
		       + 'MAS init = %d\n' % self.mas_init
	           + 'MAS mode = %d\n' % self.mas_mode
	           + 'In buff  = %d\n' % self.in_size
	           + 'In fill  = %d\n' % self.in_fill
	           + 'Received = %d %d\n' % (self.recv_hi, self.recv_lo) )

		if self.wifi_pow <= 100:
			tmp2 = 'WiFi pow = %d\n' % self.wifi_pow
		else:
			tmp2 = 'Connection = Wired\n'

		tmp3 = ( 'Jiffies  = %d\n' % self.jiffies
		       + 'Out buff = %d\n' % self.out_size
		       + 'Out fill = %d\n' % self.out_fill
		       + 'Elapsed  = %d %d\n' % (self.seconds, self.msecs)
		       + 'Voltage  = %d\n' % self.voltage
		       + 'Stamp    = %d\n' % self.stamp
		       + 'Error    = %d\n' % self.error )

		return 'STAT:\n%s%s%s' % (tmp1, tmp2, tmp3)

class Resp(Message):
	head        = 'RESP'
	http_header = None # string
	
	def __init__(self, http_header):
		self.http_header = http_header
	
	def __str__(self):
		return 'RESP: %s' % self.http_header

class Ureq(Message):
	head = 'UREQ'

	def __str__(self):
		return 'UREQ: -'



class Command:
	def serialize(self):
		raise Exception, 'All Command subclasses must implement serialize()'
	
class Strm(Command):
	# the first couple of sections are just named constants to use in the
	# "real" member values.

	# operations
	OP_START   = 's'
	OP_PAUSE   = 'p'
	OP_UNPAUSE = 'u'
	OP_STOP    = 'q'
	OP_FLUSH   = 'f'
	OP_STATUS  = 't'
	OP_SKIP    = 'a' # track or amount? probably amount. time or bytes?
	
	# autostart? ("extern" as in "extern source". e.g. internet radio.)
	AUTOSTART_NO         = '0'
	AUTOSTART_YES        = '1'
	AUTOSTART_EXTERN_NO  = '2' 
	AUTOSTART_EXTERN_YES = '3'

	# formats
	FORMAT_MPEG = 'm'
	FORMAT_WAV  = 'p' # also for AIF
	FORMAT_FLC  = 'f'
	FORMAT_WMA  = 'w' # also for ASX
	FORMAT_OGG  = 'o'
	
	# pcm sample sizes
	PCM_SIZE_8 =  '0'
	PCM_SIZE_16 = '1'
	PCM_SIZE_24 = '2'
	PCM_SIZE_32 = '3'

	# pcm KHz sample rates
	PCM_RATE_8  = '5'
	PCM_RATE_11 = '0'
	PCM_RATE_12 = '6'
	PCM_RATE_16 = '7'
	PCM_RATE_22 = '1'
	PCM_RATE_24 = '8'
	PCM_RATE_32 = '2'
	PCM_RATE_44 = '3' # 44.1, of course
	PCM_RATE_48 = '4'
	PCM_RATE_96 = '9'

	# pcm channels
	PCM_MONO   = '1'
	PCM_STEREO = '2'
	
	# pcm endianness
	PCM_BIG_ENDIAN    = '0'
	PCM_LITTLE_ENDIAN = '1'
	
	# spdif enabled?
	SPDIF_AUTO    = struct.pack('B', 0)
	SPDIF_ENABLE  = struct.pack('B', 1)
	SPDIF_DISABLE = struct.pack('B', 2)

	# fade types
	FADE_NONE  = '0'
	FADE_CROSS = '1'
	FADE_IN    = '2'
	FADE_OUT   = '3'
	FADE_INOUT = '4'

	# other flags
	FLAG_LOOP_FOREVER   = 0x80 # loop over the buffer content forever
	FLAG_DEC_NO_RESTART = 0x40 # don't restart the decoder (when do you?)
	FLAG_INVERT_RIGHT   = 0x02 # invert polarity, right channel
	FLAG_INVERT_LEFT    = 0x01 # invert polarity, left channel

	# member values to serialize follow:

	operation       = None
	autostart       = '?'
	format          = '?'
	pcm_sample_size = '?'
	pcm_sample_rate = '?'
	pcm_channels    = '?'
	pcm_endianness  = '?'
	in_threshold    = 10    # KBytes of input data to buffer before autostart
	                        # and/or notifying the server of buffer status
					        # struct.pack('B', _) 
	spdif           = SPDIF_DISABLE
	fade_time       = 0     # seconds to spend on fading between songs
	                        # struct.pack('B', _) 
	fade_type       = FADE_NONE
	flags           = 0     # struct.pack('B', _)
	out_threshold   = 1     # tenths of seconds of decoded audio to buffer
	                        # before starting playback.
	                        # struct.pack('B', _) 
	reserved        = struct.pack('B', 0)
	gain            = (0,0) # playback gain in 16.16 fixed point
	                        # struct.pack('HH', htons(_), htons(_))

	server_port     = 3484  # struct.pack('H', socket.htons(3484))
	server_ip       = 0     # where to get the data stream (32 bit IPv4 addr).
	                        # zero makes it use the same as the control server.
	                        # struct.pack('L', htonl(_))
	player_guid     = ''

	def serialize(self):
		cmd = 'strm'
		tmp = ( self.operation
		      + self.autostart
		      + self.format
		      + self.pcm_sample_size
		      + self.pcm_sample_rate
		      + self.pcm_channels
		      + self.pcm_endianness
		      + struct.pack('B', self.in_threshold)
		      + self.spdif
		      + struct.pack('B', self.fade_time)
		      + self.fade_type
		      + struct.pack('B', self.flags)
		      + struct.pack('B', self.out_threshold)
		      + self.reserved
		      + struct.pack('HH', socket.htons(self.gain[0]),
		                          socket.htons(self.gain[1]))
		      + struct.pack('H', socket.htons(self.server_port))
		      + struct.pack('L', socket.htonl(self.server_ip)) )
		if len(tmp) != 24:
			raise Exception, 'strm command not 24 bytes in length'
		params = ( tmp + 'GET /stream.mp3?player=%s HTTP/1.0\n'
		         % self.player_guid )
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Grfe(Command):
	offset     = 0    # only non-zero for the Transporter
	transition = None # char
	distance   = 32   # transition start on the Y-axis. not well understood
	bitmap     = None # 4 * 320 chars for an SB2/3 display

	def serialize(self):
		cmd    = 'grfe'
		params = ( struct.pack('H', socket.htons(self.offset))
		         + self.transition
		         + struct.pack('B', self.distance)
		         + self.bitmap )
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Grfb(Command):
	brightness = None # uint16

	def serialize(self):
		cmd    = 'grfb'
		params = struct.pack('H', socket.htons(self.brightness))
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Aude(Command):
	# what to enable/disable? true/false
	analog  = True
	digital = True
	
	def serialize(self):
		cmd    = 'aude'
		params = ( struct.pack('B', self.analog)
		         + struct.pack('B', self.digital) )
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Audg(Command):
	# gains are integer tuples: (16bit,16bit)
	# dvc (digital volume control?) is boolean
	# preamp must fit in a uint8
	# legacy is the old-style gain control. not used, send junk
	left     = (0,0)
	right    = (0,0)
	dvc      = False
	preamp   = 255  # default to maximum
	legacy   = struct.pack('LL', 0, 0)
	
	def serialize(self):
		cmd    = 'audg'
		params = ( self.legacy
		         + struct.pack('B', self.dvc)
		         + struct.pack('B', self.preamp)
		         + struct.pack('HH', socket.htons(self.left[0]),
		                             socket.htons(self.left[1]))
		         + struct.pack('HH', socket.htons(self.right[0]),
		                             socket.htons(self.right[1])) )
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Updn(Command):
	def serialize(self):
		cmd    = 'updn'
		params = ' '
		length = struct.pack('H', socket.htons(len(cmd + params)))
		return length + cmd + params



# only used to debug malformed messages
def parsable(data):
	kind = data[0:4]
	if kind in ['HELO', 'ANIC', 'IR  ', 'BYE!', 'STAT', 'RESP', 'UREQ']:
		return True
	return False

# returns a tuple (message, remainder) where message is a Message instance
# and remainder is any remaining data that was not consumed by parsing.
def parse(data):
	if len(data) < 8:
		raise Excpetion, 'Useless message, length = %d' % len(data)

	kind = data[0:4]
	dlen = socket.ntohl(struct.unpack('L', data[4:8])[0])
	body = data[8:8+dlen]
	rem  = data[8+dlen:]
	#print '\n%s %d %d' % (kind, dlen, len(body))

	if kind == 'HELO':
		if   dlen == 10:
			msg = parse_helo_10(body, dlen)
		elif dlen == 36:
			msg = parse_helo_36(body, dlen)
		return (msg, rem)

	if kind == 'ANIC':
		return (Anic(), rem)

	if kind == 'IR  ':
		return (parse_ir(body, dlen), rem)

	if kind == 'BYE!':
		return (parse_bye(body, dlen), rem)
	
	if kind == 'STAT':
		return (parse_stat(body, dlen), rem)

	if kind == 'RESP':
		return (parse_resp(body, dlen), rem)

	if kind == 'UREQ':
		return (parse_ureq(body, dlen), rem)

	print('unknown message:')
	# look for next message in the mess:
	for i in range(len(data) - 4):
		if not parsable(data[i:]):
			if ord(data[i]) >= 33 and ord(data[i]) <= 126:
				sys.stdout.write('%c ' % data[i])
			else:
				sys.stdout.write('\\%d ' % ord(data[i]))
		else:
			sys.stdout.write('\n')
			sys.stdout.flush()
			print('Recovered parsable message!')
			return (None, data[i:])
	sys.stdout.write('\n')
	sys.stdout.flush()
	return (None, '')

def parse_helo_10(data, dlen):
	id       = ord(data[0])
	revision = ord(data[1])
	tmp      = struct.unpack('6BH', data[2:])
	mac_addr = tuple(tmp[0:6])
	wlan_chn = socket.ntohs(tmp[6])
	mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr

	return Helo(id, revision, mac_addr, 1234, 'EN')

def parse_helo_36(data, dlen):
	id       = ord(data[0])
	revision = ord(data[1])
	tmp      = struct.unpack('6B16BHLL2s', data[2:])
	mac_addr = tuple(tmp[0:6])

	# why not just cook a new device number?
	if id == ID.SQUEEZEBOX2 and mac_addr[0:3] == (0x0,0x4,0x20):
		id = ID.SQUEEZEBOX3

	uuid     = ''.join(str(i) for i in tmp[6:22])
	wlan_chn = socket.ntohs(tmp[22])
	recv_hi  = socket.ntohl(tmp[23])
	recv_lo  = socket.ntohl(tmp[24])
	language = tmp[25]
	mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr

	return Helo(id, revision, mac_addr, uuid, language)

last_ir = None # tuple: (IR code, time stamp, stress)
def parse_ir(data, dlen):
	global last_ir

	stamp   = socket.ntohl(struct.unpack('L', data[0:4])[0])
	format  = struct.unpack('B', data[4:5])[0]
	nr_bits = struct.unpack('B', data[5:6])[0]
	code    = socket.ntohl(struct.unpack('L', data[6:10])[0])
	
	if code not in IR.codes_debug:
		print 'stamp   %d' % stamp
		print 'format  %d' % format
		print 'nr bits %d' % nr_bits
		print 'UNKNOWN ir code %d' % code
		last_ir = None
		return None

	stress = 0
	if last_ir and last_ir[0] == code:
		# the same key was pressed again. if it was done fast enough,
		# then we *guess* that the user is keeping it pressed, rather
		# than hitting it again real fast. unfortunately the remotes
		# don't generate key release events.
		#print('Stamp %d, diff %d' % (stamp, stamp - last_ir[1]))
		if stamp - last_ir[1] < 130: # milliseconds
			# the threshold can't be set below 108 which seems to be the
			# rate at which the SB3 generates remote events. at the same
			# time it is quite impossible to manually hit keys faster
			# than once per 140ms, so 130ms should be a good threshold.
			stress = last_ir[2] + 1
		else:
			stress = 0
	last_ir = (code, stamp, stress)
	return Tactile(code, stress)

def parse_bye(data, dlen):
	reason = struct.unpack('B', data[0])
	return Bye(reason)

def parse_stat(data, dlen):
	stat = Stat()

	stat.event    = data[0:4]
	stat.crlfs    = struct.unpack('B', data[4])[0]
	stat.mas_init = struct.unpack('B', data[5])[0]
	stat.mas_mode = struct.unpack('B', data[6])[0]
	stat.in_size  = socket.ntohl(struct.unpack('L', data[ 7:11])[0])
	stat.in_fill  = socket.ntohl(struct.unpack('L', data[11:15])[0])
	stat.recv_hi  = socket.ntohl(struct.unpack('L', data[15:19])[0])
	stat.recv_lo  = socket.ntohl(struct.unpack('L', data[19:23])[0])
	stat.wifi_pow = socket.ntohs(struct.unpack('H', data[23:25])[0])
	stat.jiffies  = socket.ntohl(struct.unpack('L', data[25:29])[0])
	stat.out_size = socket.ntohl(struct.unpack('L', data[29:33])[0])
	stat.out_fill = socket.ntohl(struct.unpack('L', data[33:37])[0])
	stat.seconds  = socket.ntohl(struct.unpack('L', data[37:41])[0])
	stat.voltage  = socket.ntohs(struct.unpack('H', data[41:43])[0])
	stat.msecs    = socket.ntohl(struct.unpack('L', data[43:47])[0])
	stat.stamp    = socket.ntohl(struct.unpack('L', data[47:51])[0])
	if stat.event == 'STMn' and dlen >= 53:
		stat.error = struct.unpack('H', data[51:53])[0]
	else:
		stat.error = 0

	if dlen > 53:
		# junk data. just ignore it.
		pass

	return stat

def parse_resp(data, dlen):
	# data is always an HTTP header. In fact the very same one we sent
	# on the streaming socket, unless the device is streaming from some
	# other source. simply discard the data for now.
	return Resp(data)

def parse_ureq(data, dlen):
	return Ureq()
