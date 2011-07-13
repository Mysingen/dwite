import os
import mutagen
import json
import re
import traceback

from magic import Magic

import protocol

from backend import Backend

class Track:
	uri = None

	def __init__(self, uri):
		self.uri = uri

class FileSystem(Backend):
	root_dir = u'/'
	name     = u'File system'

	def __init__(self, out_queue):
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'conman.json')
		if os.path.exists(path):
			f             = open(path)
			cfg           = json.load(f)
			self.root_dir = cfg['backends']['file_system']['root_dir']
			self.name     = cfg['backends']['file_system']['name']
			f.close()
		Backend.__init__(self, self.name, out_queue)

	def on_start(self):
		pass
	
	def on_stop(self):
		pass

	def handle(self, msg):
		if isinstance(msg, protocol.Ls):
			payload = self._get_children(msg.guid)
			self.out_queue.put(protocol.Listing(msg.guid, payload))
			return
		raise Exception('Unhandled message: %s' % str(msg))
	
	def _classify_file(self, path, verbose=False):
		assert type(path) == unicode
		supported = ['MPEG ADTS', 'FLAC', 'MPEG Layer 3', 'Audio', '^data$']
		ignored = ['ASCII', 'JPEG', 'PNG', 'text', '^data$', ]
		magic = Magic()

		try:
			m = magic.from_file(path.encode('utf-8'))
		except Exception as e:
			print 'INTERNAL ERROR: %s: %s' % (path, str(e))
			return (None, None, None)
		if verbose:
			print('Magic(%s):\n%s' % (path, m))

		for s in supported:
			match = re.search(s, m)
			if match:
				try:
					audio = mutagen.File(path, easy=True)
					if type(audio) == mutagen.mp3.EasyMP3:
						format = 'mp3'
					elif type(audio) == mutagen.flac.FLAC:
						format = 'flac'

					if 'title' in audio.keys():
						title = audio['title'][0]
					else:
						title = os.path.basename(path)
					assert type(title) == unicode

					duration = int(audio.info.length * 1000)

					if verbose:
						print((format, title, duration))
					return (format, title, duration)
				except AttributeError, e:
					print('Unknown file type: %s' % path)
					break
				except Exception, e:
					print('INTERNAL ERROR: FileSystem._get_children()')
					traceback.print_exc()
					self.stop()

		for i in ignored:
			if re.search(i, m):
				return (None, None, None)

		print('UNKNOWN MAGIC (%s): %s' % (path, m))
		return (None, None, None)
	
	def _get_children(self, guid, verbose=False):
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
				(format, title, duration) = self._classify_file(path)
				if format:
					size = os.path.getsize(path)
					children.append({
						'guid'    : child_guid,
						'label'   : title,
						'kind'    : format,
						'size'    : size,
						'duration': duration
					})
				else:
					children.append({
						'guid' : child_guid,
						'label': l,
						'kind' : 'file'
					})
			else:
				print('WARNING: Unsupported VFS content: %s' % path)
		return children

	def get_item(self, guid):
		return Track(os.path.join(self.root_dir, guid))

