# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import Queue

from threading import Thread

from protocol import Bark
from watchdog import Watchdog

class ContentManager(Thread):
	alive       = True
	label       = None
	wire        = None
	stream_ip   = 0
	stream_port = 0
	in_queue    = None
	out_queue   = None
	watchdog    = None
	
	def __init__(self, label, wire, stream_ip, stream_port, in_queue,out_queue):
		print('ContentManager __init__')
		Thread.__init__(self, name=label)
		self.label       = label
		self.wire        = wire
		self.stream_ip   = stream_ip
		self.stream_port = stream_port
		self.in_queue    = in_queue
		self.out_queue   = out_queue
		self.watchdog    = Watchdog(2000)

	def stop(self):
		self.wire.stop()
		self.alive = False

	def run(self):
		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
				self.watchdog.reset()
			except Queue.Empty:
				if self.watchdog.wakeup():
					self.wire.send(Bark().serialize())
				elif self.watchdog.expired():
					self.stop()
				continue
			except:
				# unknown exception. print stack trace.
				info = sys.exc_info()
				traceback.print_tb(info[2])
				print info[1]

			if isinstance(msg, Bark):
				continue

			self.out_queue.put(msg)
				
		print('%s is dead' % self.label)

