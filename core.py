#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time
import os

from Queue import Queue

# PIL dependencies
import Image
import ImageDraw
import ImageFont

from canvas  import Canvas, TextRender
from wire    import Wire, Receiver
from remote  import IR, Remote
from browser import Browser, DirTree

def main():
	queue    = Queue(100)
	wire     = Wire(port=3483)
	receiver = Receiver(wire, queue) # receiver will send messages to the queue
	canvas   = Canvas(wire)
	render   = TextRender(canvas, '/Library/Fonts/Arial.ttf', 27)
	browser  = Browser(DirTree('/', None, os.getcwd()))

	receiver.start()

	while 1:
		try:
			msg = queue.get(block=False)
			if isinstance(msg, Remote):
				if msg.code == IR.UP:
					browser.up()
				if msg.code == IR.DOWN:
					browser.down()
				if msg.code == IR.LEFT:
					browser.leave()
				if msg.code == IR.RIGHT:
					browser.enter()
		except Exception, e:
			pass

		render.render(str(browser))
		render.tick()

main()
