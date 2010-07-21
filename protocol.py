# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import struct
import socket
import json

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
# are used in communication between dwite and cleo. Commands are outbound to
# the hardware device.
# The parser produces Message instances while the Command base class has a
# virtual function serialize() that all subclasses must implement. The
# serialized representation shall be writable on the control connection's
# socket.
# to make things really funky, the SqueezeBox does not use network order to
# describe integers. It also uses different integer sizes to describe message
# and command lengths. On top of this, JSON messages must use a larger size
# field than SB messages to be useful. Joy...
#
# Device message: size field located [4:8], unsigned long, little endian.
# Device command: size field located [0:2], unsigned short, little endian.
# JSON message:   exactly like device message.


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
		if self.code > 0:
			return 'IR  : %s %d' % (IR.codes_debug[self.code], self.stress)
		else:
			return 'IR R: %s %d' % (IR.codes_debug[-self.code], self.stress)

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
	
class Dsco(Message):
	head   = 'DSCO'
	reason = 0 # uint8

	def __init__(self, reason):
		self.reason = reason

	def __str__(self):
		if self.reason == 0:
			message = 'Connection closed normally'
		elif self.reason == 1:
			message = 'Connection reset by local host'
		elif self.reason == 2:
			message = 'Connection reset by remote host'
		elif self.reason == 3:
			message = 'Connection is no longer able to work'
		elif self.reason == 4:
			message = 'Connection timed out'
		return 'DSCO: %s' % message

class Ls(Message):
	head = 'ls'
	guid = None

	def __init__(self, guid):
		self.guid = guid
	
	def __str__(self):
		return 'ls %s' % self.guid




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
	OP_SKIP    = 'a' # skip milliseconds in the output buffer
	
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
	SPDIF_AUTO    = struct.pack('<B', 0)
	SPDIF_ENABLE  = struct.pack('<B', 1)
	SPDIF_DISABLE = struct.pack('<B', 2)

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
	in_threshold    = 0     # KBytes of input data to buffer before autostart
	                        # and/or notifying the server of buffer status
					        # struct.pack('<B', _) 
	spdif           = SPDIF_DISABLE
	fade_time       = 0     # seconds to spend on fading between songs
	                        # struct.pack('<B', _) 
	fade_type       = FADE_NONE
	flags           = 0     # struct.pack('<B', _)
	out_threshold   = 0     # tenths of seconds of decoded audio to buffer
	                        # before starting playback.
	                        # struct.pack('<B', _) 
	reserved        = struct.pack('<B', 0)
	gain            = (0,0) # playback gain in 16.16 fixed point
	                        # struct.pack('<HH', htons(_), htons(_))

	server_port     = 0     # struct.pack('<H', socket.htons(3484))
	server_ip       = 0     # where to get the data stream (32 bit IPv4 addr).
	                        # zero makes it use the same as the control server.
	                        # struct.pack('<L', htonl(_))
	resource        = None  # string to identify the file/stream on a CM server
	seek            = 0     # milliseconds

	def serialize(self):
		cmd = 'strm'
		tmp = ( self.operation
		      + self.autostart
		      + self.format
		      + self.pcm_sample_size
		      + self.pcm_sample_rate
		      + self.pcm_channels
		      + self.pcm_endianness
		      + struct.pack('<B', self.in_threshold)
		      + self.spdif
		      + struct.pack('<B', self.fade_time)
		      + self.fade_type
		      + struct.pack('<B', self.flags)
		      + struct.pack('<B', self.out_threshold)
		      + self.reserved
		      + struct.pack('<HH', socket.htons(self.gain[0]),
		                           socket.htons(self.gain[1]))
		      + struct.pack('<H', socket.htons(self.server_port))
		      + struct.pack('<L', socket.htonl(self.server_ip)) )
		if len(tmp) != 24:
			raise Exception, 'strm command not 24 bytes in length'
		if self.operation == Strm.OP_START:
			s = str('GET %s HTTP/1.0\r\n'
			        'Seek-Time: %d\r\n'
			        % (self.resource, self.seek))
			params = tmp + struct.pack('%ds' % len(s), s)
			# SqueezeCenter does this (on the GET, but it's all the same). why?
			#if len(params) % 2 != 0:
			#	params = params + '\n'
		else:
			params = tmp

		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class StrmStartMpeg(Strm):
	operation = Strm.OP_START
	format    = Strm.FORMAT_MPEG

	def __init__(self, ip, port, resource, seek=0, background=False):
		print('%d %d %s %d' % (ip, port, resource, seek))
		self.server_ip     = ip
		self.server_port   = port
		self.resource      = resource
		self.seek          = seek
		self.out_threshold = 1 # should be enough for low datarate formats
		if background:
			self.autostart = Strm.AUTOSTART_NO
		else:
			self.autostart = Strm.AUTOSTART_YES

class StrmPause(Strm):
	operation = Strm.OP_PAUSE

class StrmUnpause(Strm):
	operation = Strm.OP_UNPAUSE

class StrmStop(Strm):
	operation = Strm.OP_STOP

class StrmFlush(Strm):
	operation = Strm.OP_FLUSH

class StrmSkip(Strm):
	operation = Strm.OP_SKIP
	
	def __init__(self, msecs):
		self.gain = (0, msecs) # there are many uses for this field..

class Grfe(Command):
	offset     = 0    # only non-zero for the Transporter
	transition = None # char
	distance   = 32   # transition start on the Y-axis. not well understood
	bitmap     = None # 4 * 320 chars for an SB2/3 display

	def serialize(self):
		cmd    = 'grfe'
		params = ( struct.pack('<H', socket.htons(self.offset))
		         + self.transition
		         + struct.pack('<B', self.distance)
		         + self.bitmap )
		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Grfb(Command):
	brightness = None # uint16

	def serialize(self):
		cmd    = 'grfb'
		params = struct.pack('<H', socket.htons(self.brightness))
		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Aude(Command):
	# what to enable/disable? true/false
	analog  = True
	digital = True
	
	def serialize(self):
		cmd    = 'aude'
		params = ( struct.pack('<B', self.analog)
		         + struct.pack('<B', self.digital) )
		length = struct.pack('<H', socket.htons(len(cmd + params)))
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
	legacy   = struct.pack('<LL', 0, 0)
	
	def serialize(self):
		cmd    = 'audg'
		params = ( self.legacy
		         + struct.pack('<B', self.dvc)
		         + struct.pack('<B', self.preamp)
		         + struct.pack('<HH', socket.htons(self.left[0]),
		                              socket.htons(self.left[1]))
		         + struct.pack('<HH', socket.htons(self.right[0]),
		                              socket.htons(self.right[1])) )
		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Updn(Command):
	def serialize(self):
		cmd    = 'updn'
		params = ' '
		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class Visu(Command):
	# kinds
	NONE     = 0
	VUMETER  = 1
	SPECTRUM = 2
	WAVEFORM = 3 # no documentation or example code available anywhere

	# channels
	STEREO   = 0
	MONO     = 1

	def serialize(self):
		raise Exception, 'Visu must be subclassed'

class VisuNone(Visu):
	def serialize(self):
		cmd = 'visu'
		params = ( struct.pack('<B', Visu.NONE)
		         + struct.pack('<B', 0) )
		length = struct.pack('<H', socket.htons(len(cmd + params)))
		return length + cmd + params

class VisuMeter(Visu):
	# style
	DIGITAL = 0
	ANALOG  = 1

	#number of parameters
	PARAMETERS  = 6

	# member values
	channels    = Visu.STEREO
	style       = DIGITAL
	left_pos    = 0
	left_width  = 0
	right_pos   = 0
	right_width = 0

	def __init__(self, left_pos=280,left_width=18,right_pos=302,right_width=18):
		self.left_pos    = left_pos
		self.left_width  = left_width
		self.right_pos   = right_pos
		self.right_width = right_width

	def serialize(self):
		cmd = 'visu'
		params = ( struct.pack('<B', Visu.VUMETER)
		         + struct.pack('<B', self.PARAMETERS)
		         + struct.pack('<l', socket.htonl(self.channels))
		         + struct.pack('<l', socket.htonl(self.style))
		         + struct.pack('<l', socket.htonl(self.left_pos))
		         + struct.pack('<l', socket.htonl(self.left_width))
		         + struct.pack('<l', socket.htonl(self.right_pos))
		         + struct.pack('<l', socket.htonl(self.right_width)) )
		length = struct.pack('<h', socket.htons(len(cmd + params)))
		return length + cmd + params

class VisuSpectrum(Visu):
	# bandwidth
	HIGH_BANDWIDTH = 0 # 0..22050Hz
	LOW_BANDWIDTH  = 1 # 0..11025Hz
	
	# orientation
	LEFT_TO_RIGHT = 0
	RIGHT_TO_LEFT = 1
	
	# clipping
	CLIP_NOTHING = 0 # show all subbands
	CLIP_HIGH    = 1 # clip higher subbands

	# bar intensity
	MILD   = 1
	MEDIUM = 2
	HOT    = 3

	PARAMETERS = 19

	# member values
	channels    = Visu.STEREO
	bandwidth   = HIGH_BANDWIDTH
	preemphasis = 0x10000 # dB per KHz

	left_pos           = 0
	left_width         = 160
	left_orientation   = LEFT_TO_RIGHT
	left_bar_width     = 4
	left_bar_spacing   = 1
	left_clipping      = CLIP_HIGH
	left_bar_intensity = MILD
	left_cap_intensity = HOT

	right_pos           = 160
	right_width         = 160
	right_orientation   = RIGHT_TO_LEFT
	right_bar_width     = 4
	right_bar_spacing   = 1
	right_clipping      = CLIP_HIGH
	right_bar_intensity = MILD
	right_cap_intensity = HOT

	def serialize(self):
		cmd = 'visu'
		params = ( struct.pack('<B', Visu.SPECTRUM)
		         + struct.pack('<B', self.PARAMETERS)
		         + struct.pack('<l', socket.htonl(self.channels))
		         + struct.pack('<l', socket.htonl(self.bandwidth))
		         + struct.pack('<l', socket.htonl(self.preemphasis))

		         + struct.pack('<l', socket.htonl(self.left_pos))
		         + struct.pack('<l', socket.htonl(self.left_width))
		         + struct.pack('<l', socket.htonl(self.left_orientation))
		         + struct.pack('<l', socket.htonl(self.left_bar_width))
		         + struct.pack('<l', socket.htonl(self.left_bar_spacing))
		         + struct.pack('<l', socket.htonl(self.left_clipping))
		         + struct.pack('<l', socket.htonl(self.left_bar_intensity))
		         + struct.pack('<l', socket.htonl(self.left_cap_intensity))

		         + struct.pack('<l', socket.htonl(self.right_pos))
		         + struct.pack('<l', socket.htonl(self.right_width))
		         + struct.pack('<l', socket.htonl(self.right_orientation))
		         + struct.pack('<l', socket.htonl(self.right_bar_width))
		         + struct.pack('<l', socket.htonl(self.right_bar_spacing))
		         + struct.pack('<l', socket.htonl(self.right_clipping))
		         + struct.pack('<l', socket.htonl(self.right_bar_intensity))
		         + struct.pack('<l', socket.htonl(self.right_cap_intensity)) )
		length = struct.pack('<h', socket.htons(len(cmd + params)))
		return length + cmd + params



# internal messages. used for interthread communication. not based on other
# message classes
class Connected:
	host = None
	port = 0

	def __init__(self, host, port):
		self.host = host
		self.port = port

class Accepting:
	host = None
	port = 0

	def __init__(self, host, port):
		self.host = host
		self.port = port
	


# JSON based messages. Note that there is no Command class for JSON messaging.
# all communication is done with a common tree of message classes.
class JsonMessage(Message):
	head = 'JSON'

	def dump(self):
		print('ERROR: Your JsonMessage subclass must implement dump()')
		sys.exit(1)

	def serialize(self):
		data   = self.dump()
		length = struct.pack('<L', socket.htonl(len(data)))
		return self.head + length + data

# this command is used by a content manager to hail a device manager. There
# is no reply message class.
class Hail(JsonMessage):
	label       = None
	stream_ip   = None # the ip address of the device manager's streamer
	stream_port = None # the port of the device manager's streamer

	def __init__(self, label, stream_ip, stream_port):
		self.label       = label
		self.stream_ip   = stream_ip
		self.stream_port = stream_port

	def __str__(self):
		return 'Hail(%s %d:%d)' % (self.label, self.stream_ip, self.stream_port)

	def dump(self):
		return json.dumps(['Hail', {'label'      :self.label,
		                            'stream_ip'  :self.stream_ip,
		                            'stream_port':self.stream_port}])

# used by device manager to ask content manager for a listing of the contents
# of some item by GUID. use Listing to reply.
class Ls(JsonMessage):
	guid = None

	def __init__(self, guid):
		self.guid = guid

	def __str__(self):
		return 'Ls(%s)' % self.guid
	
	def dump(self):
		return json.dumps(['Ls', {'guid': self.guid}])

# used to list the contents of a content manager item by GUID.
class Listing(JsonMessage):
	guid    = None
	listing = None

	def __init__(self, guid, listing):
		self.guid    = guid
		self.listing = listing

	def __str__(self):
		return 'Listing(%s): %s' % (self.guid, self.listing)
	
	def dump(self):
		return json.dumps(['Listing', {'guid'   :self.guid,
		                               'listing':self.listing}])

# used by content managers to send available search terms to the device
# manager. there is no reply message class.
class Terms(JsonMessage):
	terms = None

	def __init__(self, terms):
		self.terms = terms

	def __str__(self):
		return 'Terms(): %s' % self.terms
	
	def dump(self):
		return json.dumps(['Terms', {'terms': self.terms}])


def parse_json(data):
	obj  = json.loads(data)
	head = obj[0]
	body = obj[1]

	print('head, body: %s, %s' % (head, body))

	if head == 'Hail':
		return Hail(**body)
	
	if head == 'Ls':
		return Ls(**body)
	
	if head == 'Listing':
		return Listing(**body)

	if head == 'Terms':
		return Terms(**body)

	return None





# only used to debug malformed messages
def parsable(data):
	kind = data[0:4]
	if kind not in ['HELO', 'ANIC', 'IR  ', 'BYE!', 'STAT', 'RESP', 'UREQ',
	                'JSON']:
		return False
	blen = socket.ntohl(struct.unpack('<L', data[4:8])[0])
	if blen > len(data) - 8:
		return False
	return True

def human_readable(data):
	for i in range(len(data) - 1):
		if ((ord(data[i]) >= 65 and ord(data[i]) <= 90)
		or  (ord(data[i]) >= 97 and ord(data[i]) <= 122)
		or  (ord(data[i]) in [32, 45, 46, 47, 58, 95])):
			buf = buf + '%c' % data[i]
		else:
			buf = buf + '\\%03d' % ord(data[i])
	return buf

def first_unprintable(data):
	for i in range(len(data)):
		if ((ord(data[i]) not in [9, 10, 13])
		and (ord(data[i]) < 32 or ord(data[i]) > 126)):
			return i
	return len(data)

def parse_header(head):
	try:
		kind = head[0:4]
		if kind not in ['HELO', 'ANIC', 'IR  ', 'BYE!', 'STAT', 'RESP',
		                'UREQ', 'JSON', 'DSCO']:
			print('ERROR: unknown header kind %s' % kind)
		size = socket.ntohl(struct.unpack('<L', head[4:8])[0])
		return (kind, size)
	except Exception, e:
		print e
		sys.exit(1)

def parse_body(kind, size, body):
	if kind == 'HELO':
		if size == 10:
			msg = parse_helo_10(body, size)
		elif size == 36:
			msg = parse_helo_36(body, size)
		return msg

	if kind == 'ANIC':
		return Anic()

	if kind == 'IR  ':
		return parse_ir(body, size)

	if kind == 'BYE!':
		return parse_bye(body, size)
	
	if kind == 'STAT':
		return parse_stat(body, size)

	if kind == 'RESP':
		return parse_resp(body, size)

	if kind == 'UREQ':
		return parse_ureq(body, size)

	if kind == 'JSON':
		return parse_json(body)
	
	if kind == 'DSCO':
		return parse_dsco(body, size)

	print('unknown message, len %d. first 160 chars:' % size)
	print(human_readable(body))
	#sys.exit(1)
	# look for next message in the mess:
	#for i in range(len(data) - 4):
	#	if parsable(data[i:]):
	#		print('Recovered parsable message')
	#		return (None, data[i:])
	return None

def parse_helo_10(data, dlen):
	id       = ord(data[0])
	revision = ord(data[1])
	tmp      = struct.unpack('<6BH', data[2:])
	mac_addr = tuple(tmp[0:6])
	wlan_chn = socket.ntohs(tmp[6])
	mac_addr = '%02x:%02x:%02x:%02x:%02x:%02x' % mac_addr

	return Helo(id, revision, mac_addr, 1234, 'EN')

def parse_helo_36(data, dlen):
	id       = ord(data[0])
	revision = ord(data[1])
	tmp      = struct.unpack('<6B16BHLL2s', data[2:])
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

	stamp   = socket.ntohl(struct.unpack('<L', data[0:4])[0])
	format  = struct.unpack('<B', data[4:5])[0]
	nr_bits = struct.unpack('<B', data[5:6])[0]
	code    = socket.ntohl(struct.unpack('<L', data[6:10])[0])
	
	if code not in IR.codes_debug:
		print('stamp   %d' % stamp)
		print('format  %d' % format)
		print('nr bits %d' % nr_bits)
		print('UNKNOWN ir code %d' % code)
		last_ir = None
		return None

	stress = 0
	if last_ir and last_ir[0] == code:
		# the same key was pressed again. if it was done fast enough,
		# then we *guess* that the user is keeping it pressed, rather
		# than hitting it again real fast. unfortunately the remote
		# doesn't generate key release events.
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
	reason = struct.unpack('<B', data[0])
	return Bye(reason)

def parse_stat(data, dlen):
	stat = Stat()

	stat.event    = data[0:4]
	stat.crlfs    = struct.unpack('<B', data[4])[0]
	stat.mas_init = struct.unpack('<B', data[5])[0]
	stat.mas_mode = struct.unpack('<B', data[6])[0]
	stat.in_size  = socket.ntohl(struct.unpack('<L', data[ 7:11])[0])
	stat.in_fill  = socket.ntohl(struct.unpack('<L', data[11:15])[0])
	stat.recv_hi  = socket.ntohl(struct.unpack('<L', data[15:19])[0])
	stat.recv_lo  = socket.ntohl(struct.unpack('<L', data[19:23])[0])
	stat.wifi_pow = socket.ntohs(struct.unpack('<H', data[23:25])[0])
	stat.jiffies  = socket.ntohl(struct.unpack('<L', data[25:29])[0])
	stat.out_size = socket.ntohl(struct.unpack('<L', data[29:33])[0])
	stat.out_fill = socket.ntohl(struct.unpack('<L', data[33:37])[0])
	stat.seconds  = socket.ntohl(struct.unpack('<L', data[37:41])[0])
	stat.voltage  = socket.ntohs(struct.unpack('<H', data[41:43])[0])
	stat.msecs    = socket.ntohl(struct.unpack('<L', data[43:47])[0])
	stat.stamp    = socket.ntohl(struct.unpack('<L', data[47:51])[0])
	stat.error    = socket.ntohl(struct.unpack('<H', data[51:53])[0])

	return stat

def parse_resp(data, dlen):
	# data is always an HTTP header. In fact the very same one we sent
	# on the streaming socket, unless the device is streaming from some
	# other source.
	return Resp(data)

def parse_ureq(data, dlen):
	return Ureq()

def parse_dsco(data, dlen):
	reason = struct.unpack('<B', data[0])[0]
	return Dsco(reason)

