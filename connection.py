from Queue     import Empty
from threading import Thread

class Connection(Thread):
	alive       = True
	wire        = None
	in_queue    = None
	out_queue   = None
	
	def __init__(self, wire, out_queue):
		Thread.__init__(self)
		self.wire        = wire
		self.in_queue    = wire.out_queue
		self.out_queue   = out_queue
		self.label       = unicode(self.name)

	def __eq__(self, other):
		if type(self) != type(other):
			return False
		return self.name == other.name

	def __ne__(self, other):
		return not self.__eq__(other)		

	def on_start(self):
		raise Exception('Connection classes must implement on_start()')
	
	def on_stop(self):
		raise Exception('Connection classes must implement on_stop()')

	def handle(self, msg):
		raise Exception('Connection classes must implement handle(JsonMessage)')

	def stop(self, hard=False):
		self.wire.stop(hard)
		self.alive = False

	def run(self):
		self.on_start()

		while self.alive:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
			except Empty:
				if not self.wire.is_alive():
					self.stop(hard=True)
				continue
			except:
				traceback.print_exc()
				self.stop(hard=True)
				continue
			self.handle(msg)

		self.wire.stop(hard=True)
		self.on_stop()

