# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

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

from Queue   import Queue

from device   import Classic
from wire     import Wire
from protocol import ID, Helo

def main():
	try:
		queue = Queue(100)
		wire  = Wire(3483, queue)
		wire.start()
	except: # user pressed CTRL-C before the subsystems could initialize?
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]
		return

	device = None

	# wait for a HELO message from a device so that we know what device class
	# to instantiate:
	while True:
		try:
			msg = queue.get(block=True, timeout=0.5)
		except:
			# no message in the queue. try again
			continue

		# in the following, if a device class instance is created, the queue
		# for protocol events is given over to that instance. from then on
		# the main loop cannot see what is going on on the protocol wire!

		if isinstance(msg, Helo):
			print(msg)
			if (msg.id == ID.SQUEEZEBOX3
			or  msg.id == ID.SOFTSQUEEZE):
				device = Classic(wire, queue, msg.mac_addr)
				device.queue.put(msg) # let device handle Helo as well
				break

	device.start()

	try:
		while len(threading.enumerate()) > 1:
			#print threading.enumerate()
			time.sleep(0.5)
	except:
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]

	wire.stop()
	device.stop()

main()
