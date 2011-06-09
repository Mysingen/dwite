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
from wire     import SlimWire
from protocol import ID, Helo

def make_wire(queue):
	try:
		# hand the message queue to the protocol handler. SlimWire knows how
		# to connect to a device and parse messages from it. those messages can
		# then be gotten from the queue as protocol objects (see protocol.py).
		wire = SlimWire(None, 3483, queue)
		wire.start()
		return wire
	except KeyboardInterrupt:
		# the user pressed CTRL-C before the wire's socket could even start
		# accepting connctions.
		#info = sys.exc_info()
		#traceback.print_tb(info[2])
		#print info[1]
		if wire:
			wire.stop()
	return None

def make_device(queue, wire, msg):
	# in the following, if a device class instance is created, the queue
	# for events is given over to that instance. from then on the main 	loop
	# must not try to see what is going on on the protocol wire.
	if isinstance(msg, Helo):
		if (msg.id == ID.SQUEEZEBOX3
		or  msg.id == ID.SOFTSQUEEZE):
			device = Classic(wire, queue, msg.mac_addr)
			device.queue.put(msg) # let device handle Helo as well
			device.start()
			return device
	print('The core loop only handles HELO messages from devices')
	print(msg)
	return None

def main():
	# check for directory of configuration files
	path = os.environ['DWITE_CFG_DIR']
	if not os.path.exists(path):
		os.mkdir(path)
	if not os.path.isdir(path):
		raise Exception('No configuration directory "%s"' % path)

	while True:
		# create a message queue that will be used by the SlimWire protocol
		# handler to post messages from a physical device to a device manager
		# (currently only "Classic" is supported):
		queue = Queue(100)

		wire = make_wire(queue)
		if not wire:
			break
	
		# wait for a HELO message from a device so that we know what device
		# class to instantiate:
		while True:
			try:
				msg = queue.get(block=True, timeout=0.5)
				dev = make_device(queue, wire, msg)
				if dev:
					break
			except Empty:
				# no message in the queue. try again
				continue
			except KeyboardInterrupt:
				# the user pressed CTRL-C. stop the wire's thread and return.
				wire.stop()
				return

		# from here, the main loop checks for interrupts (e.g. the user hits
		# CTRL-C) and unhandled internal exceptions. if the device stops in a
		# graceful manner it will simply be restarted.
		try:
			while dev.isAlive():
				dev.join(0.5)
			# device gets restarted now. topmost while loop has not been broken
			continue
		except KeyboardInterrupt:
			dev.stop()
			sys.exit(1)
		except:
			info = sys.exc_info()
			traceback.print_tb(info[2])
			print info[1]
			dev.stop()
			sys.exit(1)


