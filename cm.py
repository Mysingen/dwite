# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

class ContentManager:
	label       = None
	wire        = None
	stream_ip   = 0
	stream_port = 0
	
	def __init__(self, label, wire, stream_ip, stream_port):
		self.label       = label
		self.wire        = wire
		self.stream_ip   = stream_ip
		self.stream_port = stream_port

