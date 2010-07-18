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

import protocol
import tactile

STOPPED  = 0
STARTING = 1
RUNNING  = 2

class Wire(Thread):
	label    = None
	state    = STOPPED
	socket   = None
	port     = 0
	receiver = None

	def __new__(cls, port, queue):
		object = Thread.__new__(cls, None, Wire.run, 'Wire', (), {})
		return object

	def __init__(self, port, queue):
		Thread.__init__(self)
		self.label = 'Wire'
		self.state = STARTING
		self.port  = port
		self.queue = queue

	def accept(self):
		if self.state != STARTING:
			print('%s.accept() called in wrong state %d'
			      % (self.label, self.state))
			sys.exit(1)
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		print('%s waiting for port %d to become available'
		      % (self.label, self.port))
		while self.state != STOPPED: # in case someone forces a full teardown.
			try:
				self.socket.bind(('', self.port))
				break
			except:
				time.sleep(0.5) # avoid spending 99% CPU time
		print('%s accepting on %d' % (self.label, self.port))

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
				print('%s connected on %d' % (self.label, self.port))
				self.state = RUNNING
				break
			except:
				pass

	def run(self):
		while self.state != STOPPED:

			if self.state == STARTING:
				self.accept()

			print('%s is listening' % self.label)
			data = ''
			while self.state == RUNNING:
				events = select.select([self.socket],[],[self.socket], 0.5)
				if len(events[2]) > 0:
					print('%s EXCEPTIONAL EVENT' % self.label)
					self.state = STOPPED
					continue
				
				if events == ([],[],[]):
					# do nothing. the select() timeout is just there to make
					# sure we can break the loop when self.state goes STOPPED.
					# the call to handle nothing ensures that stacked up events
					# get handled. wires with no stacked events are supposed
					# to return immediately.
					self.handle(None, None, None)
					continue

				if len(events[0]) > 0:
					head = self.recv(8)
					(kind, size) = protocol.parse_header(head)
					print('msg kind=%s size=%d' % (kind, size))

					body = self.recv(size)
					if size != len(body):
						print body
						print('WARNING: size field is wrong! %d != %d'
						      % (size, len(body)))
					self.handle(kind, size, body)

		self.socket.close()
		print '%s is dead' % self.label

	def handle(self, kind, size, body):
		raise Exception, 'Wire subclasses must implement handle()'

	def stop(self):
		self.state = STOPPED

	def send(self, data, force=False):
		if self.state != RUNNING and force == False:
			print('%s restarting. Dropped %s' % (self.label, data[2:6]))
			return
		left = len(data)
		while left > 0 and self.state == RUNNING:
			try:
				sent = self.socket.send(data[-left:])
				left = left - sent
			except socket.error, e:
				if e[0] == errno.ECONNRESET:
					print('%s connection reset' % self.label)
					self.state = STARTING
					return
				if e[0] == errno.EAGAIN:
					print 'send() EAGAIN'
					# temporarily unavailable. just do it again
					continue
			except Exception, e:
				print('%s: Unhandled exception %s' % (self.label, str(e)))
				sys.exit(1)

	def recv(self, size):
		body = ''
		left = size
		while left > 0 and self.state == RUNNING:
			amount = min(left, 65536)
			try:
				r = None
				r = self.socket.recv(amount)
				body = body + r
				left = left - len(r)
			except socket.error, e:
				if e[0] == errno.ECONNRESET:
					print('%s connection reset' % self.label)
					self.state = STARTING
					body = None
					break
				if e[0] == errno.EAGAIN:
					# temporarily unavailable. just do it again
					#print('%s recv() EAGAIN' % self.label)
					pass
			except Exception, e:
				print('%s: Unhandled exception %s' % (self.label, str(e)))
				sys.exit(1)
		return body


class SlimWire(Wire):
	escrow = None

	def __init__(self, port, queue):
		Wire.__init__(self, port, queue)
		self.label = 'SlimWire'

	def handle(self, kind, size, body):
		if not (kind or size or body):
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
				self.queue.put(protocol.Tactile(code, stress))
				self.escrow = None
			return ''

		message = protocol.parse_body(kind, size, body)
		if not message:
			print('WARNING: slimwire parse_body() produced NOTHING!')
			return

		elif isinstance(message, protocol.Bye):
			self.state = STARTING

		elif isinstance(message, protocol.Ureq):
			self.state = STARTING # must set this before sending UPDN to the
			# device or race conditions come crashing in.
			time.sleep(1.0)
			self.send(Updn().serialize(), force=True)
		
		elif isinstance(message, protocol.Helo):
			self.queue.put(message)

		elif isinstance(message, protocol.Tactile):
			if message.code in [tactile.IR.FORWARD, tactile.IR.REWIND]:
				timeout = datetime.now() + timedelta(milliseconds=300)
				self.escrow = (message, timeout)
				if message.stress < 5:
					# don't post an event since we can't tell
					# yet if the wants a tap or a long press.
					return
			self.queue.put(message)

		elif isinstance(message, protocol.Stat):
			self.queue.put(message)

		elif isinstance(message, protocol.Resp):
			pass

		elif isinstance(message, protocol.Anic):
			pass

		elif isinstance(message, protocol.Dsco):
			self.queue.put(message)

		else:
			print('%s: No particular handling' % message)

class JsonWire(Wire):
	def __init__(self, port, queue):
		Wire.__init__(self, port, queue)
		self.label = 'JsonWire'

	def handle(self, kind, size, body):
		if not (kind or size or body):
			return

		message = protocol.parse_body(kind, size, body)
		if not message:
			print('WARNING: jsonwire parse_body() produced NOTHING!')
			return
			
		elif isinstance(message, protocol.Hail):
			self.queue.put(message)
			
		elif isinstance(message, protocol.Listing):
			self.queue.put(message)
			
		elif isinstance(message, protocol.Terms):
			self.queue.put(message)

		else:
			print('%s: Not handled' % message)

