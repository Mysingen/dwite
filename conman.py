# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import os
import os.path
import time

from Queue     import Queue, Empty
from threading import Thread

from wire       import JsonWire, Connected
from backend_fs import FileSystem
from streamer   import Streamer, Accepting
from watchdog   import Watchdog

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
	watchdog  = None

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

	def stop(self):
		self.streamer.stop()
		self.jsonwire.stop()
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
		self.watchdog = Watchdog(2000)

		# ready to hail the DM with all necessary info about conman subsystems
		print('Conman hails')
		hail = protocol.Hail(self.backend.name, 0, streamer_port)
		self.jsonwire.send(hail.serialize())

		while self.state != STOPPED:

			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			msg = None
			try:
				msg = self.queue.get(block=True, timeout=0.5)
				self.watchdog.reset()
			except Empty:
				if self.watchdog.wakeup():
					self.jsonwire.send(protocol.Bark().serialize())
				elif self.watchdog.expired():
					self.stop()
				continue

			if isinstance(msg, protocol.Ls):
				print 'Ls'
				self.backend.in_queue.put(msg)
				continue
			
			if isinstance(msg, protocol.Listing):
				print 'Listing'
				self.jsonwire.send(msg.serialize())
				continue
			
			if isinstance(msg, protocol.Bark):
				continue

		print('Conman is dead')

