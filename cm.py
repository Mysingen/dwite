# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback

from Queue     import Queue, Empty
from threading import Thread

from protocol import Hail, Bark, JsonMessage, JsonResult
from watchdog import Watchdog

class ContentManager(Thread):
	alive       = True
	wire        = None
	stream_ip   = 0
	stream_port = 0
	in_queue    = None
	out_queue   = None
	watchdog    = None
	
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

	def stop(self, hard=False):
		self.wire.stop(hard)
		self.alive = False

	@property
	def label(self):
		return unicode(self.name)

	def run(self):
		from dwite import register_cm, unregister_cm, get_dm, msg_reg
		registered = False
		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
				self.watchdog.reset()
			except Empty:
				if self.watchdog.wakeup():
					self.wire.send(Bark(0).serialize())
				elif self.watchdog.expired():
					print '%s expired' % self.name
					self.stop(hard=True)
				continue
			except:
				traceback.print_exc()

			if type(msg) == Hail:
				assert type(msg.label)   == unicode
				assert type(msg.stream_ip)   == int
				assert type(msg.stream_port) == int
				self.name        = msg.label
				self.stream_ip   = msg.stream_ip
				self.stream_port = msg.stream_port
				try:
					register_cm(self, self.label)
					registered = True
				except Exception, e:
					msg.respond(1, unicode(e), 0, False, False)
					self.stop()
				msg.respond(0, u'EOK', 0, False, True)
				continue

			if type(msg) == JsonResult:
				print 'cm JsonResult %d' % msg.guid
				try:
					msg_reg.run_handler(msg)
				except:
					traceback.print_exc()
					print 'throwing away %s' % msg
				continue

			if type(msg) == Bark:
				continue
				
		#print('%s is dead' % self.label)
		if registered:
			unregister_cm(self.label)

