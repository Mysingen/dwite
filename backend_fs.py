# coding=utf-8

import sys
import os
import re
import traceback
import sqlite3

import mutagen
if not (hasattr(mutagen, 'version') and mutagen.version >= (1,19)):
	print('Dwite requires at least version 1.19 of Mutagen')
	sys.exit(1)

from threading import Thread
from datetime  import datetime

from magic    import Magic
from protocol import Ls, GetItem, Search, GetTerms, JsonResult, Terms
from backend  import Backend

# private message class:
class Scan(object):
	pass

class Track(object):
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

def classify_file(path, verbose=False):
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
				print('INTERNAL ERROR: get_children()')
				traceback.print_exc()
				return (None, None)

	for i in ignored:
		if re.search(i, m):
			return ('file', None)

	if verbose:
		print('UNKNOWN MAGIC (%s): %s' % (path, m))

	return ('file', None)
	
def get_children(root_dir, guid, recursive, verbose=False):
	assert type(guid) == unicode
	children = []
	if guid == '/':
		guid = ''
	path = os.path.join(root_dir, guid)
	listing = os.listdir(path)
	listing = [safe_unicode(l) for l in listing]
	listing.sort()
	for l in listing:
		path = os.path.join(root_dir, guid, l)
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
					get_children(root_dir, child_guid, recursive, verbose)
				)
		elif os.path.isfile(path):
			(format, audio) = classify_file(path)
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

def get_item(root_dir, guid, verbose=False):
	if guid == '/':
		guid = ''
	path = os.path.join(root_dir, guid)
	if not os.path.exists(path):
		return None
	if os.path.isdir(path):
		return {
			'guid'  : guid,
			'pretty': { 'label': os.path.basename(path) },
			'kind'  :'dir'
		}
	elif os.path.isfile(path):
		(format, audio) = classify_file(path)
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

def load_db():
	path = os.path.join(os.environ['DWITE_CFG_DIR'], 'conman.sqlite3')
	db_conn = sqlite3.connect(path)
	return (db_conn, db_conn.cursor())

def set_index(db_curs, term, guid):
	db_curs.execute('insert into search_index values (?,?)', (term, guid))

def get_index(db_curs, term):
	db_curs.execute('select guid from search_index where term=?', (term,))
	return [row[0] for row in db_curs]

def scan(db_conn, db_curs, root_dir, guid, recursive, verbose=False):
	assert type(guid) == unicode
	if guid == '/':
		guid = ''
	path = os.path.join(root_dir, guid)
	if verbose:
		print path
	listing = os.listdir(path)
	listing = [safe_unicode(l) for l in listing]
	listing.sort()
	for l in listing:
		path = os.path.join(root_dir, guid, l)
		if not os.path.exists(path):
			if os.path.exists(path.decode('string_escape')):
				# the filename contains characters with unknown encoding
				# and the call to safe_unicode() earlier has converted it
				# to something that can be handled without raising encoding
				# exceptions all the time.
				path = path.decode('string_escape')

		child_guid = os.path.join(guid, l)
		if os.path.isfile(path):
			(format, audio) = classify_file(path)
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
					set_index(db_curs, t, child_guid)
				continue

		if os.path.isdir(path) and recursive:
			scan(db_conn, db_curs, root_dir, child_guid, recursive, verbose)

		elif verbose:
			print('WARNING: Unsupported VFS content: %s' % path)

	db_conn.commit()

def get_terms(db_curs):
	db_curs.execute('select term from search_index')
	return set([row[0] for row in db_curs])

class FileSystem(Backend):
	root_dir = None
	db_conn  = None
	db_curs  = None

	def __init__(self, name=None, out_queue=None, root_dir=None):
		Backend.__init__(self, name, out_queue)
		self.root_dir = root_dir

	def dump_settings(self):
		return {
			'root_dir': self.root_dir,
			'name'    : self.name
		}
	
	@classmethod
	def dump_defaults(self):
		return {
			'root_dir': os.environ['HOME'],
			'name'    : u'CM ~%s' % os.environ['USER']
		}

	def on_start(self):
		# create a SQLite table with search terms if there isn't one already:
		(self.db_conn, self.db_curs) = load_db()
		try:
			self.db_curs.execute('create table search_index (term, guid)')
		except:
			pass
	
	def on_stop(self):
		self.db_conn.close()

	def handle(self, msg):
		if isinstance(msg, Ls):
			if msg.parent:
				item_guid = os.path.dirname(msg.item)
			else:
				item_guid = msg.item

			# target() runs in own thread
			def target(msg, root_dir, item_guid, recursive):
				item = get_item(root_dir, item_guid)
				if item:
					result = get_children(root_dir, item_guid, recursive)
					i = 0
					for r in result:
						msg.respond(0,u'',i,True, {'item':item,'contents':[r]})
						i += 1
					msg.respond(0, u'', i, False, {'item':item,'contents':[]})
				else:
					msg.respond(1, u'No such directory', 0, False, None)

			t = Thread(
				target=target, name='Ls(%s)' % item_guid,
				args=(msg, self.root_dir, item_guid, msg.recursive)
			)
			t.daemon = True
			t.start()
			return

		if type(msg) == GetTerms:
			msg.respond(0, u'', 0, False, list(get_terms(self.db_curs)))
			return

		if isinstance(msg, GetItem):
			item = get_item(self.root_dir, msg.item)
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

			# target() runs in own thread
			def target(msg, root_dir, terms):
				(db_conn, db_curs) = load_db()

				# add all guids indexed by the first term:
				result = set(get_index(db_curs, terms[0]))
				if len(terms) > 1:
					for t in terms[1:]:
						result &= set(get_index(db_curs, t))
				# turn all guids into items:
				if not result:
					msg.respond(1, u'Nothing found', 0, False, None)
					return
				result = list(result)
				result.sort()
				i = 0
				for guid in result:
					item = get_item(root_dir, guid)
					if not item:
						continue
					msg.respond(0, u'', i, True, [item])
					i += 1
				if i == 0:
					# this should really be a very rare occasion: the search
					# index is soooo outdated that not a single hit actually
					# corresponds to an existing file:
					msg.respond(1, u'Nothing found', 0, False, None)
				else:
					msg.respond(0, u'', i, False, [])
			
			t = Thread(
				target=target, name='Search(%s)' % ','.join(terms),
				args=(msg, self.root_dir, terms)
			)
			t.daemon = True
			t.start()
			return

		if type(msg) == Scan:
			# target() runs in own thread
			def target(msg, root_dir):
				(db_conn, db_curs) = load_db()
				scan(db_conn, db_curs, root_dir, u'', True, False)
				if msg.wire:
					msg.wire.send(Terms(0, list(get_terms(db_curs))))
			t = Thread(target=target, name='Scan()', args=(msg, self.root_dir))
			t.daemon = True
			t.start()
			return
		
		raise Exception('Unhandled message: %s' % str(msg))
	
	def get_track(self, guid):
		return Track(os.path.join(self.root_dir, guid))

