# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

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

from Queue     import Queue
from threading import Thread
from datetime  import datetime, timedelta

import protocol
import tactile

STARTING = 1
RUNNING  = 2
PAUSED   = 3
STOPPED  = 4

class Connected:
	host = None
	port = 0
	wire = None

	def __init__(self, host, port, wire):
		self.host = host
		self.port = port
		self.wire = wire

class Wire(Thread):
	label     = None
	state     = PAUSED
	socket    = None
	host      = None
	port      = 0
	accept    = True
	in_queue  = None # in_queue is used by Wire's public methods to post
	out_queue = None # messages that should be handled by the event loop.
	                 # out_queue is passed in from outside to let us post
	                 # messages to whoever instantiated the Wire.

	def __init__(self, host, port, queue, accept=True):
		Thread.__init__(self, target=Wire.run, name='Wire')
		self.label     = 'Wire'
		self.state     = STARTING
		self.host      = host
		self.port      = port
		self.accept    = accept
		self.in_queue  = Queue(100)
		self.out_queue = queue

	def stop(self):
		self.state = STOPPED

	def send(self, payload):
		self.in_queue.put(payload)

	# protected methods below. only to be called by self (incl. subclasses)

	def _accept(self):
		if self.state != STARTING:
			print('%s.accept() called in wrong state %d'
			      % (self.label, self.state))
			sys.exit(1)
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

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
				print('%s connected to %s:%d' % (self.label, address,self.port))
				self.out_queue.put(Connected(address, self.port, self))
				self.state = RUNNING
				break
			except:
				pass

	def _connect(self):
		if self.socket:
			self.socket.close()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.settimeout(0.5)
		while self.state != STOPPED:
			try:
				self.socket.connect((self.host, self.port))
				self.socket.setblocking(False)
				self.state = RUNNING
				self.out_queue.put(Connected(self.host, self.port, self))
				break
			except Exception, e:
				#print e
				time.sleep(1) # stop pointless runaway loop

	def run(self):
		while self.state != STOPPED:
		
			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			if self.state == STARTING:
				if self.accept:
					self._accept()
				else:
					self._connect()

			if self.state == RUNNING:
				print('%s is listening' % self.label)

			payload = None
			while self.state == RUNNING:
				# check first if we have payloads to send on the socket. don't
				# block on empty queue.
				if not payload:
					try:
						payload = self.in_queue.get(block=False, timeout=None)
						wlist = [self.socket]
					except:
						wlist = []

				rlist = [self.socket]
				xlist = [self.socket]
				events = select.select(rlist, wlist, xlist, 0.02)
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
					self._handle(None, None, None)
					continue

				if len(events[1]) > 0:
					# it is conceivable that outgoing payload was assigned at
					# a time when the socket was not writable. we do not wait
					# for it to become writable and just skip to receiving
					# instead. in this case the payload still remains. send it
					# now.
					if payload:
						self._send(payload)
						payload = None

				if len(events[0]) > 0:
					# all socket messages start with an 8 byte header that
					# contains some meta data: message kind and it's size.
					head = self._recv(8)
					(kind, size) = protocol.parse_header(head)
					if not kind:
						continue
					# receive the rest of the message
					body = self._recv(size)
					if size != len(body):
						print('WARNING: size field is wrong! %d != %d'
						      % (size, len(body)))
					self._handle(kind, size, body)

		self.socket.close()
		print '%s is dead' % self.label

	def _handle(self, kind, size, body):
		raise Exception, 'Wire subclasses must implement _handle()'

	def _send(self, data, force=False):
		if self.state != RUNNING and force == False:
			print('%s restarting. Dropped %s' % (self.label, data))
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
				elif e[0] == errno.EAGAIN:
					# temporarily unavailable. just do it again
					#print('%s send() EAGAIN' % self.label)
					continue
				else:
					print('Unhandled socket error %d' % e[0])
			except Exception, e:
				print('%s: Unhandled exception %s' % (self.label, str(e)))
				sys.exit(1)

	def _recv(self, size):
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
				elif e[0] == errno.EAGAIN:
					# temporarily unavailable. just do it again
					#print('%s recv() EAGAIN' % self.label)
					pass
				else:
					print('Unhandled socket error %d' % e[0])
			except Exception, e:
				print('%s: Unhandled exception %s' % (self.label, str(e)))
				sys.exit(1)
		return body


class SlimWire(Wire):
	escrow = None

	def __init__(self, host, port, queue, accept=True):
		Wire.__init__(self, host, port, queue, accept)
		self.label = 'SlimWire'

	def _handle(self, kind, size, body):
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
				self.out_queue.put(protocol.Tactile(code, stress))
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
			self._send(Updn().serialize(), force=True)
		
		elif isinstance(message, protocol.Helo):
			self.out_queue.put(message)

		elif isinstance(message, protocol.Tactile):
			if message.code in [tactile.IR.FORWARD, tactile.IR.REWIND]:
				timeout = datetime.now() + timedelta(milliseconds=300)
				self.escrow = (message, timeout)
				if message.stress < 5:
					# don't post an event since we can't tell
					# yet if the user wants a tap or a long press.
					return
			self.out_queue.put(message)

		elif isinstance(message, protocol.Stat):
			self.out_queue.put(message)

		elif isinstance(message, protocol.Resp):
			pass

		elif isinstance(message, protocol.Anic):
			pass

		elif isinstance(message, protocol.Dsco):
			self.out_queue.put(message)

		else:
			print('%s: No particular handling' % message)

class JsonWire(Wire):
	def __init__(self, host, port, queue, accept=True):
		Wire.__init__(self, host, port, queue, accept)
		self.label = 'JsonWire'

	def _handle(self, kind, size, body):
		if not (kind or size or body):
			return

		message = protocol.parse_body(kind, size, body)
		if not message:
			print('WARNING: jsonwire parse_body() produced NOTHING!')
			return
			
		elif isinstance(message, protocol.Hail):
			self.out_queue.put(message)
			
		elif isinstance(message, protocol.Listing):
			self.out_queue.put(message)
			
		elif isinstance(message, protocol.Terms):
			self.out_queue.put(message)

		elif isinstance(message, protocol.Ls):
			self.out_queue.put(message)

		elif isinstance(message, protocol.Bark):
			self.out_queue.put(message)

		else:
			print('%s: Not handled' % message)

