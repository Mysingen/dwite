# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import Queue
import random

from threading import Thread

from protocol import Bark, JsonMessage
from watchdog import Watchdog

class ContentManager(Thread):
	alive       = True
	label       = None
	wire        = None
	stream_ip   = 0
	stream_port = 0
	in_queue    = None
	out_queue   = None
	watchdog    = None
	
	msg_guids   = {}
	
	def __init__(self, label, wire, stream_ip, stream_port, in_queue,out_queue):
		assert type(stream_ip)   == int
		assert type(stream_port) == int
		print('%s __init__' % label)
		Thread.__init__(self, name=label)
		self.label       = label
		self.wire        = wire
		self.stream_ip   = stream_ip
		self.stream_port = stream_port
		self.in_queue    = in_queue
		self.out_queue   = out_queue
		self.watchdog    = Watchdog(5000)

	def __eq__(self, other):
		if type(other) != ContentManager:
			return False
		return self.label == other.label

	def __ne__(self, other):
		return not self.__eq__(other)		

	def stop(self):
		self.wire.stop()
		self.alive = False

	def run(self):
		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
				self.watchdog.reset()
			except Queue.Empty:
				if self.watchdog.wakeup():
					self.wire.send(Bark(0).serialize())
				elif self.watchdog.expired():
					print '%s expired' % self.label
					self.stop()
					#self.watchdog.reset()
				continue
			except:
				# unknown exception. print stack trace.
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]

			if isinstance(msg, Bark):
				continue

			self.out_queue.put(msg)
				
		print('%s is dead' % self.label)
	
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

