#!/usr/local/bin/python

import socket
import sys
import struct
import array
import time
import os
import traceback

from Queue import Queue

# PIL dependencies
import Image
import ImageDraw
import ImageFont

from canvas  import Canvas, TextRender, Display
from wire    import Wire, Receiver
from remote  import IR, RemoteEvent
from browser import Browser, DirTree

def main():
	queue    = Queue(100)
	wire     = Wire(port=3483)
	receiver = Receiver(wire, queue) # receiver will send messages to the queue
	canvas   = Canvas()
	render   = TextRender(canvas, '/Library/Fonts/Arial.ttf', 27)
	browser  = Browser(DirTree('/', None, os.getcwd()))

	receiver.start()
	render.render(str(browser), 2)
	canvas.redraw()
	wire.send_grfe(canvas.bitmap, Display.TRANSITION_NONE)

	brightness = [65535, 0, 1, 3, 4]
	bi = 4

	while 1:
		msg = None
		try:
			msg = queue.get(block=False)
		except Exception, e:
			if render.tick():
				canvas.redraw()
				wire.send_grfe(canvas.bitmap, Display.TRANSITION_NONE)
			time.sleep(0.01)
			continue

		try:
			if isinstance(msg, RemoteEvent):
				transition = Display.TRANSITION_NONE
				position   = 2
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
						position   = -1
				if msg.code == IR.BRIGHTNESS:
					bi = bi - 1
					if bi < 0:
						bi = 4
					wire.send_grfb(brightness[bi])
				render.render(str(browser), position)
				canvas.redraw()
				wire.send_grfe(canvas.bitmap, transition)
		except Exception, e:
			tb = sys.exc_info()[2]
			traceback.print_tb(tb)
			print e
			break
	
	receiver.stop()

main()
