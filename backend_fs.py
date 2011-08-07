# coding=utf-8

import sys
import os
import json
import re
import traceback
import sqlite3

import mutagen
if not (hasattr(mutagen, 'version') and mutagen.version >= (1,19)):
	print('Dwite requires at least version 1.19 of Mutagen')
	sys.exit(1)

from magic    import Magic
from protocol import Ls, GetItem, Search, GetTerms
from backend  import Backend

# private message class:
class Scan(object):
	pass

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
		tmp = re.compile('[^\w]|_', re.UNICODE).split(s.lower())
		terms |= set([t for t in tmp if len(t) > 2 and not is_int(t)])
	return terms

class FileSystem(Backend):
	root_dir = u'/'
	name     = u'File system'
	db_conn  = None
	db_curs  = None

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
		# load database of search indexes:
		path = os.path.join(os.environ['DWITE_CFG_DIR'], 'conman.sqlite3')
		self.db_conn = sqlite3.connect(path)
		self.db_curs = self.db_conn.cursor()
		try:
			self.db_curs.execute('create table search_index (term, guid)')
		except:
			pass
	
	def on_stop(self):
		self.db_conn.close()
		pass

	def handle(self, msg):
		if isinstance(msg, Ls):
			if msg.parent:
				item_guid = os.path.dirname(msg.item)
			else:
				item_guid = msg.item
			item = self._get_item(item_guid)
			result = self._get_children(item_guid, msg.recursive)
			msg.respond(0, u'', 0, False, { 'item':item, 'contents':result })
			return

		if type(msg) == GetTerms:
			msg.respond(0, u'', 0, False, list(self._get_terms()))
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

		if type(msg) == Scan:
			self._scan(u'', True, False)
			return
		
		raise Exception('Unhandled message: %s' % str(msg))

	def _set_index(self, term, guid):
		self.db_curs.execute(
			'insert into search_index values (?,?)', (term, guid)
		)

	def _get_index(self, term):
		self.db_curs.execute(
			'select guid from search_index where term=?', (term,)
		)
		return [row[0] for row in self.db_curs]
	
	def _get_terms(self):
		self.db_curs.execute('select term from search_index')
		return set([row[0] for row in self.db_curs])
	
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

		if verbose:
			print('UNKNOWN MAGIC (%s): %s' % (path, m))
		return ('file', None)
	
	def _get_children(self, guid, recursive, verbose=False):
		assert type(guid) == unicode
		children = []
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
				if recursive:
					children.extend(
						self._get_children(child_guid, recursive, verbose)
					)
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
				else:
					children.append({
						'guid'  : child_guid,
						'pretty': { 'label': l },
						'kind'  : 'file'
					})
			elif verbose:
				print('WARNING: Unsupported VFS content: %s' % path)
		return children

	def _get_item(self, guid, verbose=False):
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
		elif verbose:
			print('WARNING: Unsupported VFS content: %s' % path)

	def get_item(self, guid):
		return Track(os.path.join(self.root_dir, guid))

	def _scan(self, guid, recursive, verbose=False):
		assert type(guid) == unicode

		print 'scanning %s' % guid

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
			if os.path.isfile(path):
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
					for t in make_terms(title, artist, album, l):
						self._set_index(t, child_guid)
					continue
			self.db_conn.commit()

			if os.path.isdir(path) and recursive:
				self._scan(child_guid, recursive, verbose)

			elif verbose:
				print('WARNING: Unsupported VFS content: %s' % path)


if __name__ == '__main__':
	# test 1: check that make_terms splits strings with unicode characters:
	terms = make_terms(u'hellå Björk')
	assert u'hellå' in terms
	assert u'björk' in terms

