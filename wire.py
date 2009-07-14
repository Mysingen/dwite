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
from datetime  import datetime, timedelta

from protocol import *

STOPPED  = 0
STARTING = 1
RUNNING  = 2

class Wire(Thread):
	state    = STOPPED
	socket   = None
	port     = 0
	receiver = None
	escrow   = None

	def __new__(cls, port, queue):
		object = Thread.__new__(cls, None, Wire.run, 'Wire', (), {})
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
		while self.state != STOPPED: # in case someone forces a full teardown.
			try:
				self.socket.bind(('', self.port))
				break
			except:
				time.sleep(0.5) # avoid spending 99% CPU time
		print('Wire accepting on %d' % self.port)

		# socket.accept() hangs and you can't abort by hitting CTRL-C on the
		# command line (because the thread isn't the program main loop that
		# receives the resulting SIGINT), so to be able to abort we set the
		# socket to time out and then try again if self.state still permits it.
		self.socket.listen(1)
		self.socket.settimeout(0.5)
		while self.state != STOPPED:
			try:
				self.socket, address = self.socket.accept()
				self.socket.setblocking(False)
				print('Wire connected on %d' % self.port)
				self.state = RUNNING
				break
			except:
				pass

	def run(self):
		while self.state != STOPPED:

			if self.state == STARTING:
				self.accept()

			print('Wire listening')
			data = ''
			while self.state == RUNNING:
				events = select.select([self.socket],[],[self.socket], 0.5)
				if len(events[2]) > 0:
					print('Wire EXCEPTIONAL EVENT')
					self.state = STOPPED
					continue
				
				# if we wake up for any non-exceptional reason and there is a
				# tactile event in escrow, check if it has expired and if so
				# send its negative version as a signal that the key has been
				# released. this isn't completely fool proof, because the event
				# can be overwritten by one for another key before it expires.
				# i.e. first press '1' for a while and then quickly change to
				# pressing '2'. not sure if this is really a problem.
				if self.escrow and self.escrow[1] < datetime.now():
					code   = -self.escrow[0].code
					stress =  self.escrow[0].stress
					self.queue.put(Tactile(code, stress))
					print
					self.escrow = None
				
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.state goes STOPPED.
					continue

				if len(events[0]) > 0:
					try:
						data = data + self.socket.recv(1024)
					except socket.error, e:
						if e[0] == errno.ECONNRESET:
							self.state = STARTING
							continue
						print('Wire: Unhandled exception %s' % str(e))
						continue

					while parsable(data):
						(message, data) = parse(data)
						if not message:
							break

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
							self.escrow = (
								message,
								datetime.now() + timedelta(milliseconds=300)
							)
							continue

						if isinstance(message, Stat):
							self.queue.put(message)
							continue

						if isinstance(message, Resp):
							print(message)
							continue

						if isinstance(message, Anic):
							continue

						print('%s: No particular handling' % message.head)

					#for d in data:
					#	sys.stdout.write('\\%03d' % ord(d))
					#print('')


		self.socket.close()
		print 'wire is dead'

	def stop(self):
		self.state = STOPPED

	def send(self, data):
		if self.state != RUNNING:
			print('Wire restarting. Dropped %s' % data[2:6])
			return
		#print('Wire.send %s' % data[2:6])
		self.socket.send(data)
