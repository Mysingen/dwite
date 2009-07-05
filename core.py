#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time
import traceback

from device  import Classic
from wire    import Wire, Receiver

def main():
	wire     = Wire(port=3483)
	device   = Classic(wire)
	receiver = Receiver(wire, device.queue)

	device.start()
	receiver.start()

	try:
		while True:
			time.sleep(0.01)
	except Exception, e:
		tb = sys.exc_info()[2]
		traceback.print_tb(tb)
		print e

	receiver.stop()
	device.stop()

main()
