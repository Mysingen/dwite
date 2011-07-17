# Copyright 2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import random

from Queue     import Queue, Empty
from threading import Thread

from protocol import JsonMessage

class UserInterface(Thread):
	alive       = True
	wire        = None
	in_queue    = None
	out_queue   = None
	
	def __init__(self, wire, out_queue):
		Thread.__init__(self)
		self.wire        = wire
		self.in_queue    = wire.out_queue
		self.out_queue   = out_queue

	def __eq__(self, other):
		if type(other) != UserInterface:
			return False
		return self.name == other.name

	def __ne__(self, other):
		return not self.__eq__(other)		

	def stop(self):
		self.wire.stop()
		self.alive = False

	@property
	def label(self):
		return unicode(self.name)

	def run(self):
		from dwite import register_ui, unregister_ui, get_dm

		register_ui(self, u'UserInterface %s' % self.label)
		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
			except Empty:
				continue
			except:
				traceback.print_exc()

			for dm in get_dm(None):
				dm.in_queue.put(msg)
				
		print('UserInterface %s is dead' % self.label)
		unregister_ui(u'UserInterface %s' % self.label)

