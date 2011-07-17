# Copyright 2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import getopt
import time

from Queue    import Queue, Empty

from protocol import Play, JsonResult, Add
from wire     import JsonWire, Connected

def txrx(cmd):
	queue = Queue(10)
	wire  = JsonWire('', 3482, queue, accept=False)
	
	try:
		wire.start()
	
		while True:
			try:
				msg = queue.get(block=False)
			except Empty:
				time.sleep(0.1)
				continue
			if isinstance(msg, Connected):
				break
			print('Garbage messsage: %s' % unicode(msg))
	
		wire.send(cmd.serialize())

		while True:
			try:
				msg = queue.get(block=False)
			except Empty:
				time.sleep(0.1)
				continue
			if isinstance(msg, JsonResult):
				print msg
				break
			print('Garbage messsage: %s' % unicode(msg))

	except KeyboardInterrupt:
		pass
	wire.stop()

def play(argv):
	def syntax():
		print('Syntax: cli play --url cm://<cm label>/<guid> [--seek <msec>]')
		sys.exit(1)

	(opts, args) = getopt.gnu_getopt(argv, '', ['url=', 'seek='])

	url  = None
	seek = None

	for (opt, arg) in opts:
		if opt == '--url':
			url = unicode(arg)
		if opt == '--seek':
			seek = arg
	
	if not url:
		syntax()

	if seek:
		try: seek = int(seek)
		except: syntax()
	else:
		seek = 0

	cmd = Play(0, url, seek=seek)
	txrx(cmd)

def add(argv):
	def syntax():
		print('Syntax: cli add --url cm://<cm label>/<guid>')
		sys.exit(1)
	
	(opts, args) = getopt.gnu_getopt(argv, '', ['url='])
	
	url = None
	
	for (opt, arg) in opts:
		if opt == '--url':
			url = unicode(arg)
	
	if not url:
		syntax()
	
	cmd = Add(0, url)
	txrx(cmd)

