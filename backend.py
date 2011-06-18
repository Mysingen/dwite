from threading import Thread, current_thread
from Queue     import Queue, Empty

RUNNING = 1
STOPPED = 2

class Backend(Thread):
	state     = RUNNING
	name      = None
	in_queue  = None
	out_queue = None
	
	def __init__(self, name, out_queue):
		Thread.__init__(self, target=self.run, name=name)
		self.name      = name
		self.in_queue  = Queue(10)
		self.out_queue = out_queue

	def stop(self):
		self.state = STOPPED

	def run(self):
		print('starting %s' % current_thread().name)
		self.on_start()
		while self.state != STOPPED:
			try:
				msg = self.in_queue.get(block=True, timeout=0.5)
				self.handle(msg)
			except Empty:
				continue
			except Exception, e:
				print('INTERNAL ERROR: Backend.run():')
				traceback.print_exc()
				break
		self.on_stop()
		print('%s is dead' % current_thread().name)

	def on_start(self):
		raise Exception('Your backend must implement on_start()')

	def on_stop(self):
		raise Exception('Your backend must implement on_stop()')

	def get_item(self, guid):
		raise Exception('Your backend must implement get_item()')

	def handle(self, msg):
		raise Exception('Your backend must implement _handle()')

