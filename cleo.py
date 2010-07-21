#! /usr/bin/env python

import sys
import os
import os.path
import time

from Queue     import Queue
from threading import Thread

from wire     import JsonWire
from threaded_backend  import BansheeDB, POST
from streamer import Streamer

import protocol

STARTING = 1
RUNNING  = 2
PAUSED   = 3
STOPPED  = 4

class Cleo(Thread):
	label     = None
	state     = PAUSED
	backend   = None
	streamer  = None
	jsonwire  = None
	queue     = None

	def __init__(self):
		Thread.__init__(self, target=Cleo.run, name='Cleo')
		self.backend  = BansheeDB('Banshee')
		self.queue    = Queue(100)
		self.streamer = Streamer(3485, self.backend, self.queue)
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
		msg1 = self.queue.get(block=True)
		msg2 = self.queue.get(block=True)
		if isinstance(msg1, protocol.Connected):
			print('connected')
		if isinstance(msg2, protocol.Connected):
			print('connected')
		if isinstance(msg1, protocol.Accepting):
			print('accepting')
		if isinstance(msg2, protocol.Accepting):
			print('accepting')

		print('Cleo hails')
		hail = protocol.Hail(self.backend.name, 0, 3485)
		self.jsonwire.send(hail.serialize())

		while self.state != STOPPED:

			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			msg = None
			try:
				msg = self.queue.get(block=True, timeout=0.5)
			except Exception, e:
				pass

			if isinstance(msg, protocol.Ls):
				print('message Ls')
				listing = POST(self.backend.get_children, guid=msg.guid)
				payload = protocol.Listing(msg.guid, listing).serialize()
				self.jsonwire.send(payload)

			
		print('Cleo hails')
		hail = protocol.Hail(self.backend.name, 0, 3485)
		self.jsonwire.send(hail.serialize())

		print('Cleo is dead')

