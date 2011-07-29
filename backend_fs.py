import os
import mutagen
import json
import re
import traceback

from magic import Magic

from protocol import Ls, GetItem, Terms, Search

from backend import Backend

class Track:
	uri = None

	def __init__(self, uri):
		self.uri = uri

def safe_unicode(string):
	assert type(string) in [str, unicode]
	if type(string) == unicode:
		return string
	if type(string) == str:
		try:
			return string.decode('utf-8')
		except:
			return unicode(string.encode('string_escape'))

def is_int(string):
	try:
		int(string)
		return True
	except:
		return False

def make_terms(*strings):
	terms = set()
	for s in strings:
		if not s:
			continue
		tmp = re.split('[^a-zA-Z0-9]', s.lower())
		terms |= set([t for t in tmp if len(t) > 2 and not is_int(t)])
	return terms

class FileSystem(Backend):
	root_dir = u'/'
	name     = u'File system'
	index    = {} # search terms to guids

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
		if isinstance(msg, Ls):
			if msg.parent:
				item_guid = os.path.dirname(msg.item)
			else:
				item_guid = msg.item
			item = self._get_item(item_guid)
			(result, terms) = self._get_children(item_guid, msg.recursive)
			msg.respond(0, u'', 0, False, { 'item':item, 'contents':result })
			msg.wire.send(Terms(0, list(terms)).serialize())
			return

		if isinstance(msg, GetItem):
			item = self._get_item(msg.item)
			if not item:
				msg.respond(1, u'No such item', 0, False, None)
			else:
				msg.respond(0, u'', 0, False, item)
			return

		if isinstance(msg, Search):
			terms = msg.params['terms']
			if len(terms) == 0:
				msg.respond(1, u'Empty search term', 0, False, None)
				return
			# add all guids indexed by the first term:
			result = set(self._get_index(terms[0]))
			if len(terms) > 1:
				for t in terms[1:]:
					result &= set(self._get_index(t))
			# turn all guids into items:
			if not result:
				msg.respond(1, u'Nothing found', 0, False, None)
				return
			result = list(result)
			result.sort()
			result = [self._get_item(guid) for guid in result]
			msg.respond(0, u'', 0, False, result)
			return
		
		raise Exception('Unhandled message: %s' % str(msg))

	def _set_index(self, term, guid):
		if term not in self.index:
			self.index[term] = []
		self.index[term].append(guid)

	def _get_index(self, term):
		if term not in self.index:
			return []
		return self.index[term]
	
	def _classify_file(self, path, verbose=False):
		assert type(path) in [str, unicode]
		supported = ['MPEG ADTS', 'FLAC', 'MPEG Layer 3', 'Audio', '^data$']
		ignored = ['ASCII', 'JPEG', 'PNG', 'text', '^data$', 'AppleDouble']
		magic = Magic()

		try:
			if type(path) == unicode:
				m = magic.from_file(path.encode('utf-8'))
			else:
				m = magic.from_file(path)
		except Exception as e:
			print 'INTERNAL ERROR: %s: %s' % (path, str(e))
			return (None, None)
		if verbose:
			print('Magic(%s):\n%s' % (path, m))

		for s in supported:
			match = re.search(s, m)
			if match:
				try:
					audio = mutagen.File(path, easy=True)
					if type(audio) == mutagen.mp3.EasyMP3:
						return ('mp3', audio)
					elif type(audio) == mutagen.flac.FLAC:
						return ('flac', audio)
					else:
						return ('file', None)
					return (format, audio)
				except AttributeError, e:
					print('Unknown file type: %s' % path)
					break
				except mutagen.mp3.HeaderNotFoundError, e:
					print('Header not found: %s' % path)
					break
				except Exception, e:
					print('INTERNAL ERROR: FileSystem._get_children()')
					traceback.print_exc()
					self.stop()

		for i in ignored:
			if re.search(i, m):
				return ('file', None)

		print('UNKNOWN MAGIC (%s): %s' % (path, m))
		return ('file', None)
	
	def _get_children(self, guid, recursive, verbose=False):
		assert type(guid) == unicode
		children = []
		terms    = set()
		if guid == '/':
			guid = ''
		path = os.path.join(self.root_dir, guid)
		listing = os.listdir(path)
		listing = [safe_unicode(l) for l in listing]
		listing.sort()
		for l in listing:
			path = os.path.join(self.root_dir, guid, l)
			if not os.path.exists(path):
				if os.path.exists(path.decode('string_escape')):
					# the filename contains characters with unknown encoding
					# and the call to safe_unicode() earlier has converted it
					# to something that can be handled without raising encoding
					# exceptions all the time.
					path = path.decode('string_escape')

			child_guid = os.path.join(guid, l)
			if os.path.isdir(path):
				children.append({
					'guid'  : child_guid,
					'pretty': { 'label': l },
					'kind'  :'dir'
				})
				for t in make_terms(l):
					terms.add(t) # add file name to terms
					self._set_index(t, child_guid)
				if recursive:
					(c, t) = self._get_children(child_guid, recursive, verbose)
					children.extend(c)
					terms |= t # add recursive to terms
			elif os.path.isfile(path):
				(format, audio) = self._classify_file(path)
				if format in ['mp3', 'flac']:
					title = None
					if 'title' in audio.keys():
						title = audio['title'][0]
					artist = None
					if 'artist' in audio.keys():
						artist = audio['artist'][0]
					album = None
					if 'album' in audio.keys():
						album = audio['album'][0]
					n = None
					if 'tracknumber' in audio.keys():
						n = audio['tracknumber'][0]
					children.append({
						'guid'    : child_guid,
						'pretty'  : {
							'label' : l,
							'artist': artist,
							'album' : album,
							'title' : title,
							'n'     : n
						},
						'kind'    : format,
						'size'    : os.path.getsize(path),
						'duration': int(audio.info.length * 1000)
					})
					for t in make_terms(title, artist, album):
						terms.add(t) # add tag to terms
						self._set_index(t, child_guid)
				else:
					children.append({
						'guid'  : child_guid,
						'pretty': { 'label': l },
						'kind'  : 'file'
					})
					for t in make_terms(l):
						terms.add(t) # add tag to terms
						self._set_index(t, child_guid)
			else:
				print('WARNING: Unsupported VFS content: %s' % path)
		return (children, terms)

	def _get_item(self, guid):
		if guid == '/':
			guid = ''
		path = os.path.join(self.root_dir, guid)
		if not os.path.exists(path):
			return None
		if os.path.isdir(path):
			return {
				'guid'  : guid,
				'pretty': { 'label': os.path.basename(path) },
				'kind'  :'dir'
			}
		elif os.path.isfile(path):
			(format, audio) = self._classify_file(path)
			if format in ['mp3', 'flac']:
				title = None
				if 'title' in audio.keys():
					title = audio['title'][0]
				artist = None
				if 'artist' in audio.keys():
					artist = audio['artist'][0]
				album = None
				if 'album' in audio.keys():
					album = audio['album'][0]
				n = None
				if 'tracknumber' in audio.keys():
					n = audio['tracknumber'][0]
				return {
					'guid'    : guid,
					'pretty'  : {
						'label' : os.path.basename(path),
						'artist': artist,
						'album' : album,
						'title' : title,
						'n'     : n
					},
					'kind'    : format,
					'size'    : os.path.getsize(path),
					'duration': int(audio.info.length * 1000)
				}
			else:
				return {
					'guid'  : guid,
					'pretty': { 'label': os.path.basename(path) },
					'kind'  : 'file'
				}
		else:
			print('WARNING: Unsupported VFS content: %s' % path)

	def get_item(self, guid):
		return Track(os.path.join(self.root_dir, guid))

