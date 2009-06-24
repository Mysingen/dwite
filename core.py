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

from canvas  import Canvas, TextRender, Display
from wire    import Wire, Receiver
from remote  import IR, Remote
from browser import Browser, DirTree

def main():
	queue    = Queue(100)
	wire     = Wire(port=3483)
	receiver = Receiver(wire, queue) # receiver will send messages to the queue
	canvas   = Canvas()
	render   = TextRender(canvas, '/Library/Fonts/Arial.ttf', 27)
	browser  = Browser(DirTree('/', None, os.getcwd()))

	receiver.start()

	while 1:
		msg = None
		try:
			msg = queue.get(block=False)
		except Exception, e:
			time.sleep(0.01)
			continue

		try:
			if isinstance(msg, Remote):
				transition = Display.TRANSITION_NONE
				if msg.code == IR.UP:
					if browser.up():
						transition = Display.TRANSITION_SCROLL_DOWN
					else:
						transition = Display.TRANSITION_BOUNCE_DOWN
				if msg.code == IR.DOWN:
					if browser.down():
						transition = Display.TRANSITION_SCROLL_UP
					else:
						transition = Display.TRANSITION_BOUNCE_UP
				if msg.code == IR.LEFT:
					if browser.leave():
						transition = Display.TRANSITION_SCROLL_RIGHT
					else:
						transition = Display.TRANSITION_BOUNCE_RIGHT
				if msg.code == IR.RIGHT:
					if browser.enter():
						transition = Display.TRANSITION_SCROLL_LEFT
					else:
						transition = Display.TRANSITION_BOUNCE_LEFT
				render.render(str(browser))
				canvas.redraw()
				wire.send_grfe(canvas.bitmap, transition)
		except Exception, e:
			print e
			break
	
	receiver.stop()

main()
