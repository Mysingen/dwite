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

def main():
	# check for directory of configuration files
	path = os.environ['DWITE_CFG_DIR']
	if not os.path.exists(path):
		os.mkdir(path)
	if not os.path.isdir(path):
		raise Exception('No configuration directory "%s"' % path)

	try:
		# create a message queue that will be used by the SlimWire protocol
		# handler to post messages from a physical device to a device manager
		# (currently only "Classic" is supported):
		queue = Queue(100)
		# hand the message queue to the protocol handler. SlimWire knows how
		# to connect to a device and parse messages from it. those messages can
		# then be gotten from the queue as protocol objects (see protocol.py).
		wire = SlimWire(None, 3483, queue)
		wire.start()
	except KeyboardInterrupt:
		# the user pressed CTRL-C before the wire's socket could even start
		# accepting connctions.
		#info = sys.exc_info()
		#traceback.print_tb(info[2])
		#print info[1]
		if wire:
			wire.stop()
		return

	device = None

	# wait for a HELO message from a device so that we know what device class
	# to instantiate:
	while True:
		try:
			msg = queue.get(block=True, timeout=0.5)
		except Empty:
			# no message in the queue. try again
			continue
		except KeyboardInterrupt:
			# the user pressed CTRL-C. stop the wire's thread and return.
			wire.stop()
			return

		# in the following, if a device class instance is created, the queue
		# for events is given over to that instance. from then on the main loop
		# must not try to see what is going on on the protocol wire.

		if isinstance(msg, Helo):
			print(msg)
			if (msg.id == ID.SQUEEZEBOX3
			or  msg.id == ID.SOFTSQUEEZE):
				device = Classic(wire, queue, msg.mac_addr)
				device.queue.put(msg) # let device handle Helo as well
				break
		else:
			print('The core loop only handles HELO messages from devices')
			print(msg)

	device.start()

	# from here, the main loop just checks for interrupts (e.g. the user hits
	# CTRL-C) and unhandled internal exceptions. it also quits if all other
	# threads die.
	try:
		while len(threading.enumerate()) > 1:
			#print threading.enumerate()
			time.sleep(0.5)
	except KeyboardInterrupt:
		pass
	except:
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]

	wire.stop()
	device.stop()

