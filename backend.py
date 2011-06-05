from threading import Thread, current_thread
from Queue     import Queue

RUNNING = 1
STOPPED = 2

class Backend(Thread):
	state     = RUNNING
	name      = None
	in_queue  = None
	out_queue = None
	
	def __init__(self, name):
		Thread.__init__(self, target=self.run, name=name)
		self.name      = name
		self.in_queue  = Queue(10)
		self.out_queue = Queue(10)

	def stop(self):
		self.state = STOPPED

	def run(self):
		print('starting %s' % current_thread().name)
		self.on_start()
		while self.state != STOPPED:
			try:
				task = self.in_queue.get(block=True, timeout=0.5)
			except:
				continue
			self.out_queue.put(task.next())
		self.on_stop()
		print('%s is dead' % current_thread().name)

	def _post(self, generator):
		self.in_queue.put(generator)
		return self.out_queue.get()

	def on_start(self):
		raise Exception('Your backend must implement on_start()')

	def on_stop(self):
		raise Exception('Your backend must implement on_stop()')

	def get_children(self, guid):
		raise Exception('Your backend must implement get_children()')

	def get_item(self, guid):
		raise Exception('Your backend must implement get_item()')

