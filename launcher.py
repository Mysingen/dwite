#! /usr/bin/env python

# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import sys
import os
import time
import traceback
import signal
import Tkinter

if sys.version_info < (2,6):
	print("Python 2.6 or higher is required")
	sys.exit(1)
if sys.version_info >= (3,0):
	print("Python 3 not supported yet")
	sys.exit(1)

from multiprocessing import Process

os.environ['DWITE_HOME']    = os.path.dirname(os.path.realpath(sys.argv[0]))
os.environ['DWITE_CFG_DIR'] = os.path.expanduser('~/.dwite')

import dwite
import conman

class App(Tkinter.Tk):
	def __init__(self):
		self.dm = Process(target=dwite.main)
		self.cm = Process(target=conman.main, args=(sys.argv,))
		self.dm.start()
		self.cm.start()

		Tkinter.Tk.__init__(self)
		try:
			self.tk.call('console', 'hide')
		except:
			pass
		self.menu_bar = Tkinter.Menu(self)
		# a root menu with name='apple' overrides the default application
		# menu installed by Tcl/Tk:
		menu = Tkinter.Menu(self.menu_bar, name='apple')
		self.menu_bar.add_cascade(label='Dwite', menu=menu)
		self.configure(menu=self.menu_bar)
		
		self.geometry("360x310")
		label = Tkinter.Label(
			self, text=(
				'\n'
				'DISCLAIMER\n'
				'Dwite is a server for Logitech Squeezebox\n'
				'music streamers. The author of Dwite is not\n'
				'affiliated with Logitech in any way. Dwite is\n'
				'distributed "as is" with absolutely no guarantees\n'
				'of any kind. "Squeezebox" is a trademark owned\n'
				'by Logitech.\n'
				'\n'
				'SUPPORT\n'
				'Do not contact Logitech with support questions\n'
				'about Dwite. Instead contact the author by email:\n'
				'Klas Lindberg <klas.lindberg@gmail.com>\n'
				'\n'
				'COPYING\n'
				'Copyright Klas Lindberg <klas.lindberg@gmail.com>\n'
				'Dwite is distributed under the GNU General Public\n'
				'License, version 3.\n'
				'\n'
			),
			font='TkSmallCaptionFont'
		)
		label.pack()

		self.bind_all('<Command-q>', self.quit)
		self.protocol('WM_DELETE_WINDOW', self.quit)

	def quit(self, event=None):
		os.kill(self.dm.pid, signal.SIGINT)
		os.kill(self.cm.pid, signal.SIGINT)
		sys.exit(0)

if __name__ == '__main__':
	app = App()
	try:
		app.mainloop()
	except KeyboardInterrupt:
		print 'Goodbye'
