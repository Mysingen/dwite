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

STOPPED  = 0
STARTING = 1
RUNNING  = 2

class Wire(Thread):
	state    = STOPPED
	socket   = None
	port     = 0
	receiver = None

	def __new__(cls, port, queue):
		object = Thread.__new__(cls, None, Wire.run, 'Wire', (), {})
		Wire.__init__(object, port, queue)
		return object

	def __init__(self, port, queue):
		Thread.__init__(self)
		self.state = STARTING
		self.port  = port
		self.queue = queue

	def accept(self):
		if self.state != STARTING:
			print('Wire.accept() called in wrong state %d' % self.state)
			sys.exit(1)
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('Wire waiting for port %d to become available' % self.port)
		while True:
			try:
				self.socket.bind(('', self.port))
				break
			except:
				time.sleep(0.5) # avoid spending 99% CPU time
		print('Accepting on %d' % self.port)

		self.socket.listen(1)
		self.socket, address = self.socket.accept()
		print('Connected on %d' % self.port)
		self.state = RUNNING

	def run(self):
		while self.state != STOPPED:

			if self.state == STARTING:
				self.accept()

			print('Listening')
			data = ''
			while self.state == RUNNING:
				events = select.select([self.socket],[],[self.socket], 0.5)
				if len(events[2]) > 0:
					print('wire EXCEPTIONAL EVENT')
					self.state = STOPPED
					continue
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.state goes STOPPED.
					continue

				try:
					data = data + self.socket.recv(1024)
				except socket.error, e:
					if e[0] == errno.ECONNRESET:
						self.state = STARTING
						continue
					print('Receiver: Unhandled exception %s' % str(e))
					continue

				while len(data) >= 8:
					(message, data) = parse(data)

					if isinstance(message, Bye):
						self.state = STARTING
						print(message)
						continue

					if isinstance(message, Ureq):
						self.state = STARTING
						print(message)
						time.sleep(1.0)
						# bypass self.send() to not drop outgoing command
						self.socket.send(Updn().serialize())
						continue

					if isinstance(message, Helo):
						self.queue.put(message)
						continue

					if isinstance(message, Tactile):
						self.queue.put(message)
						continue
					
					print('%s: No particular handling' % message.head)

		self.socket.close()
		print 'wire is dead'

	def stop(self):
		self.state = STOPPED

	def send(self, data):
		if self.state != RUNNING:
			print('Wire restarting. Dropped %s' % data[2:6])
			return
		self.socket.send(data)
