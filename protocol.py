class ID:
	SQUEEZEBOX   = 2
	SOFTSQUEEZE  = 3
	SQUEEZEBOX2  = 4
	TRANSPORTER  = 5
	SOFTSQUEEZE3 = 6
	RECEIVER     = 7
	SQUEEZESLAVE = 8
	CONTROLLER   = 9
	SQUEEZEBOX3  = 104 # not reported by firmware, but infered from HELO msg.

	debug = {
		SQUEEZEBOX   : 'SqueezeBox',
		SOFTSQUEEZE  : 'SoftSqueeze',
		SQUEEZEBOX2  : 'SqueezeBox_2',
		TRANSPORTER  : 'Transporter',
		SOFTSQUEEZE3 : 'SoftSqueeze_3',
		RECEIVER     : 'Receiver',
		SQUEEZESLAVE : 'SqueezeSlave',
		CONTROLLER   : 'Controller',
		SQUEEZEBOX3  : 'SqueezeBox_3'
	}

class ProtocolEvent:
	pass

class HeloEvent:
	def __init__(self, id, revision, mac_addr, uuid, language):
		self.id       = id       # integer
		self.revision = revision # integer
		self.mac_addr = mac_addr # string
		self.uuid     = uuid     # string
		self.language = language # string

	def __str__(self):
		return '%s %d %s %s %s' % (ID.debug[self.id], self.revision,
		                           self.mac_addr, self.uuid, self.language)
