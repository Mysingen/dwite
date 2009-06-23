#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time

# PIL dependencies
import Image
import ImageDraw
import ImageFont

from canvas import Canvas, TextRender
from wire   import Wire


def main():
# 	myHost = ''
# 	myPort = 3483
# 	
# 	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# 	while (1):
# 		try:
# 			s.bind((myHost, myPort))
# 			break
# 		except socket.error, msg:
# 			pass # waiting (endlessly?) for port to become available
# 	print 'listen()'
# 	s.listen(1)
# 
# 	connection, address = s.accept()

	wire   = Wire(port=3483)
	canvas = Canvas(wire)
	render = TextRender(canvas, '/Library/Fonts/Arial.ttf', 27)

	browser = ['Hello', 'cruel', 'world']
	index   = 0

	while 1:
		render.render(browser[index])
		render.tick()
		index = index + 1
		if index == 3:
			index = 0
		time.sleep(1)

# 	while (1):
# 		data = connection.recv(1024)
# 		dlen = struct.unpack('L', data[4:8])
# 		dlen = socket.ntohl(dlen[0])
# 		print '\n%s %d %d' % (data[0:4], dlen, len(data))
# 
# 		if data[0:4] == 'HELO':
# 			handle_helo(s, data[8:], dlen)
# 			continue
# 
# 		if data[0:4] == 'ANIC':
# 			continue
# 
# 		render.tick()
# 
# 		if data[0:4] == 'IR  ':
# 			handle_ir(s, data[8:], dlen)
# 			continue
# 
# 		if data[0:4] == 'BYE!':
# 			handle_bye(s, data[8:], dlen)
# 			break
# 
# 		print 'unknown message'
# 		print ['%x' % ord(c) for c in data]
# 
# 	connection.close()

main()
