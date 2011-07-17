# Copyright 2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import traceback
import re

from Queue     import Queue, Empty
from threading import Thread

from protocol  import Play, JsonResult, GetItem, Add
from menu      import make_item
from device    import PlayItem, AddItem
from cm        import ContentManager

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

	def stop(self, hard=False):
		self.wire.stop(hard)
		self.alive = False

	@property
	def label(self):
		return unicode(self.name)

	def run(self):
		from dwite import register_ui, unregister_ui, get_dm, get_cm, msg_reg

		try:
			register_ui(self, u'UserInterface %s' % self.label)
		except Exception, e:
			print e
			self.stop()
		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
			except Empty:
				if not self.wire.is_alive():
					self.stop(hard=True)
				continue
			except:
				traceback.print_exc()
				self.stop(hard=True)
				continue

			if type(msg) == JsonResult:
				print 'ui JsonResult %d' % msg.guid
				try:
					msg_reg.run_handler(msg)
				except:
					print 'throwing away %s' % msg
				continue

			if type(msg) in [Play, Add]:
				print 'ui Play/Add %s' % msg
				match = re.match(
					'(?P<scheme>^.+?)://(?P<cm>.+?)/(?P<guid>.+)', msg.url
				)
				if not match:
					errstr = u'Invalid URL format: %s' % msg.url
					msg.respond(1, errstr, 0, False, False)
					continue
				scheme = match.group('scheme')
				label  = match.group('cm')
				guid   = match.group('guid')
				if scheme != u'cm':
					errstr = u'Invalid URL scheme: %s' % msg.url
					msg.respond(2, errstr, 0, False, False)
					continue
				cm = get_cm(label)
				if not cm:
					errstr = u'No such CM: %s' % label
					msg.respond(3, errstr, 0, False, False)
					continue
				get = GetItem(msg_reg.make_guid(), guid)

				# warning: handler executed by CM thread:
				def handle_get_item(msg_reg, msg, orig_msg, cm):
					if msg.errno:
						orig_msg.respond(msg.errno, msg.errstr, 0, False, False)
						return
					item = make_item(cm, msg.result)
					for dm in get_dm(None):
						if type(orig_msg) == Play:
							cmd = PlayItem(
								orig_msg.guid,orig_msg.wire,item,orig_msg.seek
							)
						elif type(orig_msg) == Add:
							cmd = AddItem(orig_msg.guid, orig_msg.wire, item)
						dm.in_queue.put(cmd)

				msg_reg.set_handler(get, handle_get_item, cm, msg)
				cm.wire.send(get.serialize())
				continue
				

		#print('UserInterface %s is dead' % self.label)
		unregister_ui(u'UserInterface %s' % self.label)
		self.wire.stop(hard=True)

