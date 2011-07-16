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

from Queue    import Queue, Empty

from device   import Classic
from wire     import SlimWire, JsonWire, UiWire
from protocol import ID, Helo, Hail
from cm       import ContentManager

def make_dm(dm_wire, queue, msg):
	# in the following, if a device class instance is created, the queue
	# for events is given over to that instance. from then on the main 	loop
	# must not try to see what is going on on the protocol wire.
	if isinstance(msg, Helo):
		if (msg.id == ID.SQUEEZEBOX3
		or  msg.id == ID.SOFTSQUEEZE):
			device = Classic(dm_wire, queue, msg.mac_addr)
			queue.put(msg) # let device class handle Helo as well
			device.start()
			return device
	print(
		'The core loop only handles HELO messages from devices and Hail '
		'messages from content managers'
	)
	print(msg)
	return None

def make_cm(cm_wire, in_queue, out_queue, msg):
	cm = ContentManager(
		msg.label, cm_wire, msg.stream_ip, msg.stream_port, in_queue,
		out_queue
	)
	cm.start()
	return cm

def main():
	# check for directory of configuration files
	path = os.environ['DWITE_CFG_DIR']
	if not os.path.exists(path):
		os.mkdir(path)
	if not os.path.isdir(path):
		raise Exception('No configuration directory "%s"' % path)

	# device and content managers. the device manager is threaded.
	dm = None
	cm = None
	# threaded "wire" objects handle the socket connections with devices,
	# content managers and user interfaces.
	ui_wire = None
	dm_wire = None
	cm_wire = None
	
	# the queue is really owned by the DM, but created here so that it can be
	# passed to everyone else who must post messages to the DM.
	dm_queue = Queue(100)
	cm_queue = Queue(100)
	# can only wait on dm's and cm's queues when expecting HELO or Hail:
	wait_dm = False
	wait_cm = False

	try:
		while True:
			# the wires die when their respective device or content manager
			# disconnect. simply create new ones if that happens.
			if not (ui_wire and ui_wire.isAlive()):
				ui_wire = UiWire('', 3482, dm_queue)
				ui_wire.start()
			if not (dm_wire and dm_wire.isAlive()):
				dm_wire = SlimWire('', 3483, dm_queue)
				dm_wire.start()
				wait_dm = True
			if not (cm_wire and cm_wire.isAlive()):
				if dm:
					dm.rem_cm(cm)
				cm_wire = JsonWire('', 3484, cm_queue)
				cm_wire.start()
				wait_cm = True

			# wait for a HELO or Hail message from a device or CM.
			if wait_dm:
				try:
					msg = dm_queue.get(block=False)
					if isinstance(msg, Helo):
						print 'HELO'
						dm = make_dm(dm_wire, dm_queue, msg)
						wait_dm = False # stop listening on this queue
						if cm:
							dm.add_cm(cm)
				except Empty:
					pass
			if wait_cm:
				try:
					msg = cm_queue.get(block=False)
					if isinstance(msg, Hail):
						print 'Hail'
						cm = make_cm(cm_wire, cm_queue, dm_queue, msg)
						if dm:
							dm.add_cm(cm)
						wait_cm = False # stop listening on this queue
				except Empty:
					pass
			time.sleep(0.1)
	except KeyboardInterrupt:
		# the user pressed CTRL-C
		pass
	except:
		# unknown exception. print stack trace.
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]

	# stop all threaded objects and quit
	if dm:
		dm.stop()
	if cm:
		cm.stop()
	if ui_wire:
		ui_wire.stop()
	if dm_wire:
		dm_wire.stop()
	if cm_wire:
		cm_wire.stop()

