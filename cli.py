# Copyright 2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

from Queue    import Queue, Empty

from protocol import Play, JsonResult
from wire     import JsonWire, Connected

def run(cmd, url, seek):
	assert cmd == 'play'
	queue = Queue(10)
	wire  = JsonWire('', 3482, queue, accept=False)
	
	try:
		wire.start()
	
		while True:
			try:
				msg = queue.get(block=True, timeout=0.1)
			except Empty:
				continue
			if isinstance(msg, Connected):
				break
			print('Garbage messsage: %s' % unicode(msg))
	
		msg = Play(0, url, seek=seek)
		wire.send(msg.serialize())

		while True:
			try:
				msg = queue.get(block=True, timeout=0.1)
			except Empty:
				continue
			if isinstance(msg, JsonResult):
				print msg
				break
			print('Garbage messsage: %s' % unicode(msg))

	except KeyboardInterrupt:
		pass
	wire.stop()
	wire.join()

