import os
import mutagen
import json

from backend import Backend

class Track:
	uri = None

	def __init__(self, uri):
		self.uri = uri

class FileSystem(Backend):
	root_dir = u'/'
	name     = u'File system'

	def __init__(self):
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'cleo.json')
		if os.path.exists(path):
			f             = open(path)
			cfg           = json.load(f)
			self.root_dir = cfg['backends']['file_system']['root_dir']
			self.name     = cfg['backends']['file_system']['name']
			f.close()
		
		Backend.__init__(self, self.name)
		
	
	def on_start(self):
		pass
	
	def on_stop(self):
		pass
	
	def get_children(self, guid):
		children = []
		if guid == '/':
			guid = ''
		path = os.path.join(self.root_dir, guid)
		listing = os.listdir(path)
		listing.sort()
		for l in listing:
			path = os.path.join(self.root_dir, guid, l)
			child_guid = os.path.join(guid, l)
			if os.path.isdir(path):
				children.append({'guid':child_guid, 'label':l, 'kind':'dir'})
			elif os.path.isfile(path):
				try:
					audio = mutagen.File(path, easy=True)
					if type(audio) == mutagen.mp3.EasyMP3:
						if 'title' in audio.keys():
							title = audio['title'][0]
						else:
							title = l
						children.append({
							'guid'    : child_guid,
							'label'   : title,
							'kind'    : 'mp3',
							'size'    : os.path.getsize(path),
							'duration': int(audio.info.length * 1000)
						})
					else:
						children.append({
							'guid':child_guid, 'label':l, 'kind':'file'
						})
				except AttributeError, e:
					print "Unknown file type: %s" % path
			else:
				print('WARNING: Unsupported VFS content: %s' % path)
		return children

	def get_item(self, guid):
		return Track(os.path.join(self.root_dir, guid))

