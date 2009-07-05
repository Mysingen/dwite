#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time
import traceback
import threading

from device  import Classic
from wire    import Wire, Receiver

def main():
	try:
		wire     = Wire(port=3483)
		device   = Classic(wire)
		receiver = Receiver(wire, device.queue)
	except: # user pressed CTRL-C before the subsystems could initialize fully?
		return

	device.start()
	receiver.start()

	try:
		while len(threading.enumerate()) > 1:
			#print threading.enumerate()
			time.sleep(0.5)
	except:
		print('') # print the diagnostic on a clean, new line
		info = sys.exc_info()
		traceback.print_tb(info[2])
		print info[1]

	receiver.stop()
	device.stop()

main()
