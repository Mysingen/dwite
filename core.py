#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time
import traceback
import threading

from Queue   import Queue

from device   import Classic
from wire     import Wire, Receiver
from protocol import ID, HeloEvent

def main():
	try:
		queue    = Queue(100)
		wire     = Wire(port=3483)
		receiver = Receiver(wire, queue)
	except: # user pressed CTRL-C before the subsystems could initialize fully?
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]
		return
	receiver.start()

	# wait for a HELO message from a device so that we know what device class
	# to instantiate:
	while True:
		try:
			msg = queue.get(block=True, timeout=0.1)
		except:
			# no message in the queue. try again
			continue

		# in the following, if a device class instance is created, the queue
		# on which protocol events is given over to that instance. from then
		# on, the main loop cannot see what is going on on the protocol wire!

		if isinstance(msg, HeloEvent):
			if (msg.id == ID.SQUEEZEBOX3
			or  msg.id == ID.SOFTSQUEEZE):
				device = Classic(wire, queue, msg.mac_addr)
				break
			print('HELO from %s' % str(msg))

	device.start()

	try:
		while len(threading.enumerate()) > 1:
			#print threading.enumerate()
			time.sleep(0.5)
	except:
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]

	receiver.stop()
	device.stop()

main()
