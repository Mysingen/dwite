#!/usr/local/bin/python

import socket
import sys
import struct
import array

# PIL dependencies
import Image
import ImageDraw
import ImageFont

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

def handle_helo(s, data, len):
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

def handle_ir(s, data, len):
	time    = struct.unpack('L', data[0:4])[0]
	format  = struct.unpack('B', data[4:5])[0]
	nr_bits = struct.unpack('B', data[5:6])[0]
	code    = struct.unpack('L', data[6:10])[0]
	
	print 'time    %d' % time
	print 'format  %d' % format
	print 'nr bits %d' % nr_bits
	if code in ir_codes:
		print 'ir code %s' % ir_codes[code]
	else:
		print 'ir code %d' % code

def handle_bye(s, data, len):
	reason = struct.unpack('B', data[0])
	if reason == 1:
		print 'Player is going out for an upgrade'

def render_text(string):
	image = Image.new('1', (320, 32), 0)
	draw  = ImageDraw.Draw(image)
	font  = ImageFont.truetype('/Library/Fonts/Arial.ttf', 27)
	draw.text((0,0), string, font=font, fill=1)
	# transpose before outputting to the SqueezeBox. the full image is composed
	# of 320 stripes of 32 bits each, running from top to bottom. each 8-bit part
	# of each stripe has to be sent in reverse.
	#image = image.transpose(Image.ROTATE_270)
	#image = image.transpose(Image.FLIP_LEFT_RIGHT)

	for y in [8, 16, 24, 32]:
		box = (0, y-8, 320, y)
		sub = image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
		image.paste(sub, box)
	image.save('blaha.png', 'PNG')

	pack = []
	data = list(image.getdata()) # len() == 320*32

	for i in range(320):
		# pack each stripe into an unsigned 32 bit integer.
		stripe = 0
		for j in range(32):
			stripe = stripe | (data[j * 320 + i] << j)
		pack.append(struct.pack('L', stripe))
	return ''.join(pack)

def one(i):
	print i
	return struct.pack('L', (2**32)-1 & ~(1 << i))

def send_grfe(s):
	b0 = 128
	b1 = 129
	b2 = 130
	b3 = 134
	cmd = 'grfe'
	offset = socket.htons(0)
	offset = struct.pack('H', offset)
	transition = ' ' # ' ' 'l' 'r' 'u' 'd' (scroll) 'L' 'R' 'U' 'D' (bounce)
	distance = struct.pack('B', 0)

	bitmap = render_text('Hejsan')
	
	payload = cmd + offset + transition + distance + bitmap
	length = socket.htons(len(payload))
	length = struct.pack('H', length)

	s.send(length + cmd + offset + transition + distance + bitmap)

def main():
	myHost = ''
	myPort = 3483
	
	render_text('Hejsan')
#	sys.exit(0)
		
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	while (1):
		try:
			s.bind((myHost, myPort))
			break
		except socket.error, msg:
			pass # waiting (endlessly?) for port to become available
	print 'listen()'
	s.listen(1)

	connection, address = s.accept()

	try:
		while (1):
			data = connection.recv(1024)
			dlen = struct.unpack('L', data[4:8])
			dlen = socket.ntohl(dlen[0])
			print '\n%s %d %d' % (data[0:4], dlen, len(data))
	
			if data[0:4] == 'HELO':
				handle_helo(s, data[8:], dlen)
				continue
	
			if data[0:4] == 'ANIC':
				continue
			
			send_grfe(connection)

			if data[0:4] == 'IR  ':
				handle_ir(s, data[8:], dlen)
				continue

			if data[0:4] == 'BYE!':
				handle_bye(s, data[8:], dlen)
				break

			print 'unknown message'
			print ['%x' % ord(c) for c in data]

	except Exception, msg:
		print msg

	connection.close()

main()
