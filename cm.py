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

