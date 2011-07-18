# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import os
import os.path
import time
import traceback
import random

from Queue     import Queue, Empty
from threading import Thread

from wire       import JsonWire, Connected
from backend_fs import FileSystem
from streamer   import Streamer, Accepting

import protocol

STARTING = 1
RUNNING  = 2
PAUSED   = 3
STOPPED  = 4

class Conman(Thread):
	label     = None
	state     = PAUSED
	backend   = None
	streamer  = None
	jsonwire  = None
	queue     = None
	handlers  = {}

	def __init__(self):
		Thread.__init__(self, target=Conman.run, name='Conman')
		self.queue    = Queue(100)
		self.backend  = FileSystem(self.queue)
		self.streamer = Streamer(self.backend, self.queue)
		self.jsonwire = JsonWire('', 3484, self.queue, accept=False)
		self.backend.start()
		self.streamer.start()
		self.jsonwire.start()
		self.state    = RUNNING

	def get_handler(self, msg):
		if msg.guid in self.handlers:
			return self.handlers[msg.guid]
		return None

	def stop(self, hard=False):
		self.streamer.stop()
		self.jsonwire.stop(hard)
		self.backend.stop()
		self.state = STOPPED

	def run(self):
		# wait for other subsystems to come up before going on
		todo = 2
		while todo > 0:
			msg = self.queue.get(block=True)
			if isinstance(msg, Connected):
				todo -= 1
			if isinstance(msg, Accepting):
				streamer_port = msg.port
				todo -= 1

		# ready to hail the DM with all necessary info about conman subsystems
		def handle_hail(self, msg, orig_msg, user):
			assert type(msg) == protocol.JsonResult
			if msg.errno:
				print msg.errstr
				self.stop()
		guid = random.randint(1, 1000000)
		hail = protocol.Hail(guid, self.backend.name, 0, streamer_port)
		self.handlers[guid] = (hail, handle_hail, None)
		self.jsonwire.send(hail.serialize())

		while self.state != STOPPED:

			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			msg = None
			try:
				msg = self.queue.get(block=True, timeout=0.5)
			except Empty:
				if not self.jsonwire.is_alive():
					self.stop(hard=True)
				continue
			except Exception, e:
				print 'VERY BAD!'
				traceback.print_exc()

			if isinstance(msg, protocol.Ls):
				self.backend.in_queue.put(msg)
				continue
			
			if isinstance(msg, protocol.JsonResult):
				if msg.guid in self.handlers:
					(orig_msg, handler, user) = self.get_handler(msg)
					handler(self, msg, orig_msg, user)
				else:
					print msg
				continue

			if isinstance(msg, protocol.GetItem):
				self.backend.in_queue.put(msg)

		#print('Conman is dead')

