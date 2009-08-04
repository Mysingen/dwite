# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

from render import ProgressRender

class Seeker:
	guid     = 0
	limit    = 0
	position = 0
	render   = None

	def __init__(self, guid, limit, position):
		self.guid     = guid
		self.limit    = limit
		self.position = position
		self.render   = ProgressRender()
	
	def seek(self, msec):
		target = self.position + msec
		if target < 0:
			print('Can\'t seek to before position 0')
			target = 0
		if target > self.limit:
			print('Can\'t seek beyond %d' % self.limit)
			target = self.limit
		self.position = target
		self.render.curry(float(self.position) / self.limit)

	def ticker(self):
		return (self.guid, self.render)

