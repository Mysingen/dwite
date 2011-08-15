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
import getopt
import threading
import json

from Queue     import Queue, Empty
from threading import Thread

from wire       import JsonWire, Connected
from backend_fs import FileSystem, Scan
from streamer   import Streamer, Accepting
from protocol   import JsonResult, Hail, Ls, GetItem

STARTING = 1
RUNNING  = 2
PAUSED   = 3
STOPPED  = 4

class Conman(Thread):
	label     = None
	state     = STARTING
	backend   = None
	streamer  = None
	jsonwire  = None
	queue     = None
	handlers  = {}
	connected = False
	accepting = False

	def __init__(self):
		Thread.__init__(self, target=Conman.run, name='Conman')
		settings = self.load_settings()
		self.queue    = Queue(100)
		self.backend  = FileSystem(out_queue=self.queue, **settings['backend'])
		self.streamer = Streamer(self.backend, self.queue)
		self.jsonwire = JsonWire('', 3484, self.queue, accept=False)
		self.backend.start()
		self.streamer.start()
		self.jsonwire.start()

	def load_settings(self):
 		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'conman.json')
		settings = {}
		if os.path.exists(path):
			f = open(path)
			try:
				settings = json.load(f)
			except:
				print('ERROR: Could not load settings file %s' % path)
				settings = {}
			f.close()

		if 'backend' not in settings:
			settings['backend'] = FileSystem.dump_defaults()
		return settings

	def save_settings(self):
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'conman.json')
		try:
			f = open(path, 'w')
			settings = json.load(f)
			f.close()
		except:
			settings = {'backend':{}}
		settings['backend'] = self.backend.dump_settings()
		f = open(path, 'w')
		json.dump(settings, f, indent=4)
		f.close()

	def get_handler(self, msg):
		if msg.guid in self.handlers:
			return self.handlers[msg.guid]
		return None

	def stop(self, hard=False):
		self.streamer.stop()
		self.jsonwire.stop(hard)
		self.backend.stop()
		self.state = STOPPED

	def send_hail(self):
		def handle_hail(self, msg, orig_msg, user):
			assert type(msg) == JsonResult
			if msg.errno:
				print msg.errstr
				self.stop()
		guid = random.randint(1, 1000000)
		hail = Hail(guid, self.backend.name, 0, self.streamer.port)
		self.handlers[guid] = (hail, handle_hail, None)
		self.jsonwire.send(hail.serialize())

	def run(self):
		while self.state != STOPPED:

			if self.state == PAUSED:
				time.sleep(0.5)
				continue

			msg = None
			try:
				msg = self.queue.get(block=True, timeout=0.5)
			except Empty:
				if (not self.jsonwire.is_alive()) and self.state == RUNNING:
					self.state = STARTING
					self.connected = False
					self.jsonwire = JsonWire('', 3484, self.queue, accept=False)
					self.jsonwire.start()
				continue
			except Exception, e:
				print 'VERY BAD!'
				traceback.print_exc()

			if type(msg) in [Accepting, Connected]:
				self.connected |= (type(msg) == Connected)
				self.accepting |= (type(msg) == Accepting)
				if self.connected and self.accepting and self.state == STARTING:
					# ready to hail the DM with all necessary info about conman
					# subsystems
					self.send_hail()
					self.state = RUNNING
				continue

			if isinstance(msg, JsonResult):
				if msg.guid in self.handlers:
					(orig_msg, handler, user) = self.get_handler(msg)
					handler(self, msg, orig_msg, user)
				else:
					print msg
				continue

			self.backend.in_queue.put(msg)

		self.save_settings()

def syntax():
	print('Syntax: conman [--scan]')
	sys.exit(1)

def main(argv):
	path = os.environ['DWITE_CFG_DIR']
	if not os.path.isdir(path):
		raise Exception('No configuration directory "%s"' % path)

	try:
		(opts, args) = getopt.gnu_getopt(sys.argv, '', ['scan'])
	except:
		syntax()

	scan = False
	for (opt, arg) in opts:
		if opt == '--scan':
			scan = True

	try:
		cm = Conman()
		if scan:
			cm.queue.put(Scan())
		cm.start()
		while True:
			if cm.is_alive():
				time.sleep(0.5)
			else:
				break
	except KeyboardInterrupt:
		pass
	except:
		traceback.print_exc()

	cm.stop(hard=True)

	while True:
		print [t.name for t in threading.enumerate()]
		target = threading.active_count() - 1
		for t in threading.enumerate():
			if t.daemon:
				target -= 1
		if target == 0:
			break
		time.sleep(1)

