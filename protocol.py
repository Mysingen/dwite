# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import struct
import socket

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
	pass

class Helo(Message):
	def __init__(self, id, revision, mac_addr, uuid, language):
		self.id       = id       # integer
		self.revision = revision # integer
		self.mac_addr = mac_addr # string
		self.uuid     = uuid     # string
		self.language = language # string

	def __str__(self):
		return 'HELO: %s %d %s %s %s' % (ID.debug[self.id], self.revision,
		                           self.mac_addr, self.uuid, self.language)

class Ureq(Message):
	def __str__(self):
		return 'UREQ: -'

class Command:
	def serialize(self):
		raise Exception, 'All Command subclasses must implement serialize()'
	
class Strm(Command):
	# the first couple of sections are just named constants to use in the
	# "real" member values.

	# operations
	OP_START = 's'
	OP_PAUSE = 'p'
	OP_STOP  = 'q'
	OP_FLUSH = 'f'
	
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
	transition = 'c'  # default is no transition effect
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
