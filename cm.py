# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback

from connection import Connection
from protocol   import Hail, JsonMessage, JsonResult, Terms

class CmConnection(Connection):
	label       = None
	stream_ip   = 0
	stream_port = 0
	registered  = False
	
	def __init__(self, wire, out_queue):
		Connection.__init__(self, wire, out_queue)

	def on_start(self):
		pass
	
	def on_stop(self):
		from dwite import unregister_cm
		if self.registered:
			unregister_cm(self.label)

	def handle(self, msg):
		from dwite import register_cm, get_dm, msg_reg

		if type(msg) == Hail:
			assert type(msg.label)   == unicode
			assert type(msg.stream_ip)   == int
			assert type(msg.stream_port) == int
			self.label       = msg.label
			self.stream_ip   = msg.stream_ip
			self.stream_port = msg.stream_port
			try:
				register_cm(self, self.label)
				self.registered = True
			except Exception, e:
				msg.respond(1, unicode(e), 0, False, False)
				self.stop()
				return
			msg.respond(0, u'EOK', 0, False, True)
			return

		if type(msg) == JsonResult:
			#print 'cm JsonResult %d' % msg.guid
			try:
				msg_reg.run_handler(msg)
			except:
				traceback.print_exc()
				print 'throwing away %s' % msg
			return

		if type(msg) == Terms:
			msg.sender = self.label
			for dm in get_dm(None):
				dm.in_queue.put(msg)
			return

		raise Exception('Unhandled message: %s' % msg)

