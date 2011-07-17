# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import socket
import sys
import struct
import array
import time
import traceback
import threading
import os
import random

from Queue    import Queue, Empty

from device   import Device
from wire     import SlimWire, JsonWire, Connected
from cm       import ContentManager
from ui       import UserInterface
from protocol import JsonMessage

class MessageRegister(object):
	handlers = {}
	
	def make_guid(self):
		while True:
			guid = random.randint(1, 1000000)
			if guid not in self.handlers:
				return guid

	def set_handler(self, msg, handler, user, override_orig_msg=None):
		assert isinstance(msg, JsonMessage)
		assert (msg.guid > 0) and (msg.guid not in self.handlers)
		if override_orig_msg:
			self.handlers[msg.guid] = (override_orig_msg, handler, user)
		else:
			self.handlers[msg.guid] = (msg, handler, user)

	def get_handler(self, msg):
		assert isinstance(msg, JsonMessage)
		if msg.guid in self.handlers:
			return self.handlers[msg.guid]
		return (None, None, None)

	def rem_handler(self, msg):
		assert isinstance(msg, JsonMessage)
		assert msg.guid in self.handlers
		del self.handlers[msg.guid]

	def run_handler(self, msg):
		(orig_msg, handler, user) = self.get_handler(msg)
		if not handler:
			raise Exception('No handler for %d' % msg.guid)
		self.rem_handler(msg)
		handler(self, msg, orig_msg, user)

# global registry of message handlers
msg_reg = MessageRegister()

# device, content and ui managers. everything is threaded.
dms = {}
cms = {}
uis = {}

def register_cm(cm, label):
	if label in cms:
		raise Exception('A CM with label "%s" is already registered' % label)
	print 'register CM %s' % label
	assert type(label) == unicode
	cms[label] = cm
	for dm in dms.values():
		dm.add_cm(cm)

def unregister_cm(label):
	print 'unregister CM %s' % label
	assert type(label) == unicode
	for dm in dms.values():
		dm.rem_cm(cms[label])
	del cms[label]

def get_cm(label):
	if not label:
		return cms.values()
	assert type(label) == unicode
	if label in cms:
		return cms[label]
	return None

def register_ui(ui, label):
	if label in uis:
		raise Exception('A UI with label "%s" is already registered' % label)
	print 'register UI %s' % label
	assert type(label) == unicode
	uis[label] = ui

def unregister_ui(label):
	print 'unregister UI %s' % label
	assert type(label) == unicode
	del uis[label]

def register_dm(dm, label):
	if label in dms:
		raise Exception('A DM with label "%s" is already registered' % label)
	print 'register DM %s' % label
	assert type(label) == unicode
	dms[label] = dm
	for cm in cms.values():
		dm.add_cm(cm)

def unregister_dm(label):
	print 'unregister DM %s' % label
	assert type(label) == unicode
	del dms[label]

def get_dm(label):
	if not label:
		return dms.values()
	assert type(label) == unicode
	if label in dms:
		return dms[label]
	return None

def main():
	# check for directory of configuration files
	path = os.environ['DWITE_CFG_DIR']
	if not os.path.exists(path):
		os.mkdir(path)
	if not os.path.isdir(path):
		raise Exception('No configuration directory "%s"' % path)

	# a queue to be used by all newly created wires to drop messages here.
	queue = Queue(100)

	try:
		# threaded "wire" objects handle the socket connections with devices,
		# content managers and user interfaces.
		ui_wire = JsonWire('', 3482, queue, accept=True)
		dm_wire = SlimWire('', 3483, queue, accept=True)
		cm_wire = JsonWire('', 3484, queue, accept=True)
		ui_wire.start()
		dm_wire.start()
		cm_wire.start()

		# wait for Connected messages from the wires. whenever one gets
		# connected create a new one so that more devices, etc, can connect
		# to dwite.
		while True:
			msg = None
			try:
				msg = queue.get(block=True, timeout=0.1)
			except Empty:
				continue

			if type(msg) == Connected:
				if msg.wire == ui_wire:
					UserInterface(ui_wire, queue).start()
					ui_wire = JsonWire('', 3482, queue, accept=True)
					ui_wire.start()
				elif msg.wire == dm_wire:
					# we need more information about the remote end before a
					# fully proper DM representation can be created. in the
					# meanwhile we still have to do *something*, so we use
					# the base class Device as a placeholder. it will make the
					# necessary corrections itself when more about the remote
					# end becomes known.
					Device(dm_wire, queue).start()
					dm_wire = SlimWire('', 3483, queue, accept=True)
					dm_wire.start()
				elif msg.wire == cm_wire:
					ContentManager(cm_wire, queue).start()
					cm_wire = JsonWire('', 3484, queue, accept=True)
					cm_wire.start()
				continue

			raise Exception('INTERNAL ERROR: Garbage message: %s' % msg)

	except KeyboardInterrupt:
		# the user pressed CTRL-C
		pass
	except:
		traceback.print_exc()

	# stop all threaded objects and quit
	ui_wire.stop(hard=True)
	dm_wire.stop(hard=True)
	cm_wire.stop(hard=True)
	for dm in dms.values():
		dm.stop()
	for cm in cms.values():
		cm.stop()
	for ui in uis.values():
		ui.stop()

	while threading.active_count() > 1:
		print [t.name for t in threading.enumerate()]
		time.sleep(1)

