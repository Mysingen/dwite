import os

def get_path(name):
	return '%s/fonts/%s.ttf' % (os.getenv('DWITE_HOME'), name)

