# Copyright 2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import re

from protocol   import Play, JsonResult, GetItem, Add
from menu       import make_item
from device     import PlayItem, AddItem
from connection import Connection

class UiConnection(Connection):
	alive       = True
	wire        = None
	in_queue    = None
	out_queue   = None
	registered  = False
	
	def __init__(self, wire, out_queue):
		Connection.__init__(self, wire, out_queue)
		self.label = u'UiConnection %s' % self.label

	def on_start(self):
		from dwite import register_ui
		try:
			register_ui(self, self.label)
			self.registered = True
		except Exception, e:
			print e
			self.stop()

	def on_stop(self):
		from dwite import unregister_ui
		if self.registered:
			unregister_ui(self.label)

	def handle(self, msg):
		from dwite import get_dm, get_cm, msg_reg

		if type(msg) == JsonResult:
			#print 'ui JsonResult %d' % msg.guid
			try:
				msg_reg.run_handler(msg)
			except:
				print 'throwing away %s' % msg
			return

		if type(msg) in [Play, Add]:
			#print 'ui Play/Add %s' % msg
			match = re.match(
				'(?P<scheme>^.+?)://(?P<cm>.+?)/(?P<guid>.+)', msg.url
			)
			if not match:
				errstr = u'Invalid URL format: %s' % msg.url
				msg.respond(1, errstr, 0, False, False)
				return
			scheme = match.group('scheme')
			label  = match.group('cm')
			guid   = match.group('guid')
			if scheme != u'cm':
				errstr = u'Invalid URL scheme: %s' % msg.url
				msg.respond(2, errstr, 0, False, False)
				return
			cm = get_cm(label)
			if not cm:
				errstr = u'No such CM: %s' % label
				msg.respond(3, errstr, 0, False, False)
				return
			get = GetItem(msg_reg.make_guid(), guid)

			# warning: handler executed by CM thread:
			def handle_get_item(msg_reg, msg, orig_msg, cm):
				if msg.errno:
					orig_msg.respond(msg.errno, msg.errstr, 0, False, False)
					return
				item = make_item(cm.label, **msg.result)
				for dm in get_dm(None):
					if type(orig_msg) == Play:
						cmd = PlayItem(
							orig_msg.guid, orig_msg.wire, item, orig_msg.seek
						)
					elif type(orig_msg) == Add:
						cmd = AddItem(orig_msg.guid, orig_msg.wire, item)
					dm.in_queue.put(cmd)

			msg_reg.set_handler(get, handle_get_item, cm, msg)
			cm.wire.send(get.serialize())
			return
		
		raise Exception('Unhandled message: %s' % msg)

