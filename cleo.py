#! /usr/bin/env python

import sys
import os
import os.path
import time

from Queue     import Queue
from threading import Thread

from wire     import JsonWire
from backend  import BansheeDB
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
		self.streamer = Streamer(3485, self.backend)
		self.queue    = Queue(100)
		self.jsonwire = JsonWire('', 3484, self.queue, accept=False)
		self.streamer.start()
		self.jsonwire.start()
		self.state    = RUNNING

	def stop(self):
		self.streamer.stop()
		self.jsonwire.stop()
		self.state = STOPPED

	def run(self):
		while self.state != STOPPED:

			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			msg = None
			try:
				msg = self.queue.get(block=True, timeout=0.5)
			except Exception, e:
				pass

			if isinstance(msg, protocol.Connected):
				print('Cleo hails')
				hail = protocol.Hail(self.backend.pretty, 0, 3485)
				self.jsonwire.send(hail.serialize())

			if isinstance(msg, protocol.Ls):
				print('message Ls')
				listing = self.backend.get_children(msg.guid)
				payload = protocol.Listing(msg.guid, listing).serialize()
				self.jsonwire.send(payload)

			
		print('Cleo hails')
		hail = protocol.Hail(self.backend.pretty, 0, 3485)
		self.jsonwire.send(hail.serialize())

		print('Cleo is dead')

