# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import socket
import struct
import select
import sys
import traceback
import time
import errno

from threading import Thread
from datetime  import datetime

from protocol import *

class Receiver(Thread):
	wire    = None
	queue   = None
	alive   = True

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
				events = select.select([sock],[],[sock], 0.5)
				if len(events[2]) > 0:
					print('wire EXCEPTIONAL EVENT')
					break
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.alive goes false.
					continue

				try:
					data = data + self.wire.socket.recv(1024)
				except socket.error, e:
					if e[0] == errno.ECONNRESET:
						self.wire.accept()
						continue
					print('Receiver: Unhandled exception %s' % str(e))
					continue

				while len(data) >= 8:
					(message, data) = parse(data)
					if isinstance(message, Bye):
						self.alive = False
						print(str(Bye))
						break
					if isinstance(message, Ureq):
						print('UREQ handling not implemented')
						time.sleep(1.0)
						self.wire.send(Updn().serialize())
					if isinstance(message, Helo):
						self.queue.put(message)
					if isinstance(message, Tactile):
						print message
						self.queue.put(message)

		except:
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
		print 'receiver is dead'

	def stop(self):
		self.alive = False

class Wire:
	socket = None
	port   = 0

	def __init__(self, port):
		self.port = port
		self.accept(port)

	def accept(self, port=0):
		if port == 0 and self.port != 0:
			port = self.port

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
		self.socket.close()

	def send(self, data):
		self.socket.send(data)
