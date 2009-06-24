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
from canvas  import *
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
				transition = TRANSITION_NONE
				if msg.code == IR.UP:
					if browser.up():
						transition = TRANSITION_SCROLL_UP
					else:
						transition = TRANSITION_BOUNCE_DOWN
				if msg.code == IR.DOWN:
					if browser.down():
						transition = TRANSITION_SCROLL_DOWN
					else:
						transition = TRANSITION_BOUNCE_UP
				if msg.code == IR.LEFT:
					if browser.leave():
						transition = TRANSITION_SCROLL_LEFT
					else:
						transition = TRANSITION_BOUNCE_LEFT
				if msg.code == IR.RIGHT:
					if browser.enter():
						transition = TRANSITION_SCROLL_RIGHT
					else:
						transition = TRANSITION_BOUNCE_RIGHT
				render.render(str(browser), transition)
				continue
		except Exception, e:
			pass

#		render.render(str(browser), transition)
#		render.tick()
		time.sleep(0.01)

main()
