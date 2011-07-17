# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import random

from Queue     import Queue, Empty
from threading import Thread

from protocol import Hail, Bark, JsonMessage
from watchdog import Watchdog

class ContentManager(Thread):
	alive       = True
	wire        = None
	stream_ip   = 0
	stream_port = 0
	in_queue    = None
	out_queue   = None
	watchdog    = None
	
	msg_guids   = {}
	
	def __init__(self, wire, out_queue):
		Thread.__init__(self, name='ContentManager')
		self.wire        = wire
		self.in_queue    = wire.out_queue
		self.out_queue   = out_queue
		self.watchdog    = Watchdog(5000)

	def __eq__(self, other):
		if type(other) != ContentManager:
			return False
		return self.name == other.name

	def __ne__(self, other):
		return not self.__eq__(other)		

	def stop(self):
		self.wire.stop()
		self.alive = False

	@property
	def label(self):
		return unicode(self.name)

	def run(self):
		from dwite import register_cm, unregister_cm, get_dm

		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
				self.watchdog.reset()
			except Empty:
				if self.watchdog.wakeup():
					self.wire.send(Bark(0).serialize())
				elif self.watchdog.expired():
					print '%s expired' % self.name
					self.stop()
				continue
			except:
				traceback.print_exc()

			if type(msg) == Hail:
				print msg
				assert type(msg.label)   == unicode
				assert type(msg.stream_ip)   == int
				assert type(msg.stream_port) == int
				self.name        = msg.label
				self.stream_ip   = msg.stream_ip
				self.stream_port = msg.stream_port
				register_cm(self, self.label)
				continue

			if type(msg) == Bark:
				continue

			for dm in get_dm(None):
				dm.in_queue.put(msg)
				
		print('%s is dead' % self.label)
		unregister_cm(self.label)
	
	def make_msg_guid(self):
		while True:
			guid = random.randint(1, 1000000)
			if guid not in self.msg_guids:
				return guid

	def set_msg_handler(self, msg, handler):
		assert isinstance(msg, JsonMessage)
		assert msg.guid not in self.msg_guids
		self.msg_guids[msg.guid] = (msg, handler)

	def get_msg_handler(self, msg):
		assert isinstance(msg, JsonMessage)
		if msg.guid in self.msg_guids:
			return self.msg_guids[msg.guid]
		return None

	def rem_msg_handler(self, msg):
		assert isinstance(msg, JsonMessage)
		assert msg.guid in self.msg_guids
		del self.msg_guids[msg.guid]

