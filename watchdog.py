from datetime import datetime, timedelta

class Watchdog:
	value = 0    # int, milliseconds
	timer = None # datetime object
	sleep = None # datetime object

	def __init__(self, timeout):
		if type(timeout) != int:
			raise Exception('Invalid Watchdog(timeout): %s' % str(timeout))
		self.value = timeout

	def wakeup(self):
		if self.sleep and self.sleep < datetime.now():
			self.sleep = None
			return True
		return False

	def expired(self):
		return self.timer < datetime.now()

	def reset(self):
		self.sleep = datetime.now() + timedelta(milliseconds=1000)
		self.timer = datetime.now() + timedelta(milliseconds=1000 + self.value)
		
