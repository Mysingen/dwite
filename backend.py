# -*- coding: utf-8 -*-

# Copyright 2009-2011 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

import time
import os.path

from sqlite3   import dbapi2
from threading import Thread, current_thread
from Queue     import Queue

import db_row

class Item:
	# permissible kinds
	DIR  = 'dir'
	MP3  = 'mp3'
	FILE = 'file'

	guid  = None
	label = None
	kind  = None

	def __init__(self, guid, label, kind):
		self.guid  = guid
		self.label = label or '<UNKNOWN>'
		self.kind  = kind
		if self.label:
			self.label = self.label.encode("utf-8")

	def __repr__(self):
		return self.label

	def json(self):
		return {'guid' : self.guid,
		        'label': self.label,
		        'kind' : self.kind}

class Artist(Item):
	library_id = None

	def __init__(self, row, db, library_id):
		Item.__init__(self, 'artist:%d' % row.ArtistID, row.Name, Item.DIR)
		self.db         = db
		self.library_id = library_id

	def get_children(self):
		def query_db():
			q = "select * from CoreAlbums where ArtistID=? and AlbumID in "\
				"(select distinct(AlbumID) from CoreTracks where "\
				"PrimarySourceID=?) order by Title"
			rows = self.db.sql_execute(q, self.guid.split(':')[1],
			                           self.library_id)
			for row in rows:
				yield Album(row, self.db)
		return query_db()

#	def get_child_count(self):
#		q = "select count(AlbumID) as c from CoreAlbums where ArtistID=? and "\
#			"AlbumID in (select distinct(AlbumID) from CoreTracks where "\
#			"PrimarySourceID=?) "
#		return self._db.sql_execute(q, self.itemID,
#									self._local_music_library_id)[0].c

class Album(Item):

	def __init__(self, row, db):
		Item.__init__(self, 'album:%d' % row.AlbumID, row.Title, Item.DIR)
		self.db = db

	def get_children(self):
		def query_db():
			q = "select * from CoreTracks where AlbumID=? order by TrackNumber"
			rows = self.db.sql_execute(q, self.guid.split(':')[1])
			for row in rows:
				yield Track(row, self.db, self)
		return query_db()

#	def get_child_count(self):
#		q = "select count(TrackID) as c from CoreTracks where AlbumID=?"
#		count = self._db.sql_execute(q, self.itemID)[0].c
#		return count

class Track(Item):
	album    = None
	uri      = None
	size     = None
	duration = None

	def __init__(self, row, db, album):
		if row.Uri.lower().endswith('.mp3'):
			label = row.Title
			kind  = Item.MP3
		else:
			label = os.path.basename(row.Uri)
			kind  = Item.FILE
		Item.__init__(self, 'track:%d' % row.TrackID, label, kind)
		self.db       = db
		self.album    = album
		self.uri      = row.Uri
		self.size     = row.FileSize
		self.duration = row.Duration

	def json(self):
		return {'guid'    : self.guid,
		        'label'   : self.label,
		        'kind'    : self.kind,
		        'size'    : self.size,
		        'duration': self.duration}

	def get_children(self):
		return []
	
	def get_child_count(self):
		return 0

class SQLiteDB:
	db        = None
	db_params = None

	def __init__(self, db_path):
		self.db_params = {'database': db_path, 'check_same_thread': True}
		self.connect()

	def connect(self):
		self.db = dbapi2.connect(**self.db_params)

	def disconnect(self):
		self.db.close()

	def reconnect(self):
		self.disconnect()
		self.connect()

	def sql_execute(self, request, *params, **kw):
		t0        = time.time()
		debug_msg = request
		#if params:
		#	debug_msg = u"%s params=%r" % (request, params)
		#debug_msg = u''.join(debug_msg.splitlines())
		#if debug_msg:
		#	print('QUERY: %s', debug_msg)

		cursor = self.db.cursor()
		result = []
		cursor.execute(request, params)
		if cursor.description:
			all_rows = cursor.fetchall()
			result = db_row.getdict(all_rows, cursor.description)
		cursor.close()
		delta = time.time() - t0
		#print("SQL request took %s seconds" % delta)
		return result


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

class BansheeDB(Backend):
	db_path    = None
	db         = None
	library_id = None

	def __init__(self, name):
		Backend.__init__(self, name)
	
	def on_start(self):
		self.open_db(os.path.expanduser("~/.config/banshee-1/banshee.db"))
		self.library_id = self.get_library_id()

	def on_stop(self):
		self.close_db()

	def open_db(self, path):
		self.db = SQLiteDB(path)

	def close_db(self):
		self.db.disconnect()

	def get_library_id(self):
		q   = 'select PrimarySourceID from CorePrimarySources where StringID=?'
		row = self.db.sql_execute(q, 'MusicLibrarySource-Library')[0]
		return row.PrimarySourceID

	def get_item(self, guid):
		def do_it(guid):
			if guid == '/':
				yield Item('/', self.name, Item.DIR)

			if guid == '/Artists':
				yield Item('/Artists', 'Artists', Item.DIR)

			if guid == '/Albums':
				yield Item('/Albums', 'Albums', Item.DIR)

			(kind, uid) = guid.split(':')
			if kind == 'artist':
				yield self._get_artist_with_id(uid)

			if kind == 'album':
				yield self._get_album_with_id(uid)

			if kind == 'track':
				yield self._get_track_with_id(uid)
		return self._post(do_it(guid))

	def get_children(self, guid):
		def do_it(guid):
			if guid == '/':
				yield [Item('/Artists', 'Artists', Item.DIR).json(),
				        Item('/Albums',  'Albums',  Item.DIR).json()]

			if guid == '/Artists':
				yield [a.json() for a in self._get_artists()]

			if guid == '/Albums':
				yield [a.json() for a in self._get_albums()]

			(kind, uid) = guid.split(':')
			if kind == 'artist':
				albums = self._get_artist_with_id(uid).get_children()
				yield [a.json() for a in albums]
		
			if kind == 'album':
				tracks = self._get_album_with_id(uid).get_children()
				yield [t.json() for t in tracks]
		return self._post(do_it(guid))


	def _get_artists(self):
		def query_db():
			q = "select * from CoreArtists where ArtistID in "\
				"(select distinct(ArtistID) from CoreTracks where "\
				"PrimarySourceID=?) order by Name"
			for row in self.db.sql_execute(q, self.library_id):
				yield Artist(row, self.db, self.library_id)

		return query_db()

	def _get_albums(self):
		def query_db():
			q = "select * from CoreAlbums where AlbumID in "\
				"(select distinct(AlbumID) from CoreTracks where "\
				"PrimarySourceID=?) order by Title"
			for row in self.db.sql_execute(q, self.library_id):
				yield Album(row, self.db)

		return query_db()

	'''
	def get_music_playlists(self):
		return self.get_playlists(self.library_id,
								  MusicPlaylist,
								  MusicSmartPlaylist)

	def get_playlists(self, source_id, PlaylistClass, SmartPlaylistClass):
		playlists = []

		def query_db():
			q = 'select * from CorePlaylists where PrimarySourceID=? order '\
				'by Name'
			for row in self.db.sql_execute(q, source_id):
				playlist = PlaylistClass(row, self)
				playlists.append(playlist)
				yield playlist

			q = 'select * from CoreSmartPlaylists where PrimarySourceID=? '\
				'order by Name'
			for row in self.db.sql_execute(q, source_id):
				playlist = SmartPlaylistClass(row, self)
				playlists.append(playlist)
				yield playlist

		return query_db()
	'''
	def _get_artist_with_id(self, artist_id):
		q = "select * from CoreArtists where ArtistID=? limit 1"
		row = self.db.sql_execute(q, artist_id)[0]
		return Artist(row, self.db, self.library_id)
	'''
	def get_artist_with_name(self, name):
		q = "select * from CoreArtists where Name=? limit 1"
		row = self.db.sql_execute(q, name)[0]
		return Artist(row, self.db, self.library_id)
	'''
	def _get_album_with_id(self, album_id):
		q = "select * from CoreAlbums where AlbumID=? limit 1"
		row = self.db.sql_execute(q, album_id)[0]
		artist = self._get_artist_with_id(row.ArtistID)
		return Album(row, self.db)
	'''
	def get_playlist_with_id(self, playlist_id, PlaylistClass):
		q = "select * from CorePlaylists where PlaylistID=? limit 1"
		row = self.db.sql_execute(q, playlist_id)[0]
		return PlaylistClass(row, self)

	def get_smart_playlist_with_id(self, playlist_id, PlaylistClass):
		q = "select * from CoreSmartPlaylists where SmartPlaylistID=? limit 1"
		row = self.db.sql_execute(q, playlist_id)[0]
		return PlaylistClass(row, self)

	def get_music_playlist_with_id(self, playlist_id):
		return self.get_playlist_with_id(playlist_id, MusicPlaylist)

	def get_music_smart_playlist_with_id(self, playlist_id):
		return self.get_smart_playlist_with_id(playlist_id, MusicSmartPlaylist)
	'''
	def _get_track_with_id(self, track_id):
		q = "select * from CoreTracks where TrackID=? limit 1"
		row = self.db.sql_execute(q, track_id)[0]
		album = self._get_album_with_id(row.AlbumID)
		return Track(row, self.db, album)
	'''
	def get_track_for_uri(self, track_uri):
		q = "select * from CoreTracks where Uri=? limit 1"
		try:
			row = self.db.sql_execute(q, track_uri)[0]
		except IndexError:
			# not found
			track = None
		else:
			album = self.get_album_with_id(row.AlbumID)
			track = Track(row, self, album)
		return track

	def get_tracks(self):
		tracks = []
		albums = {}

		def query_db():
			q = "select * from CoreTracks where TrackID in "\
				"(select distinct(TrackID) from CoreTracks where "\
				"PrimarySourceID=?) order by AlbumID,TrackNumber"
			for row in self.db.sql_execute(q, self.self.library_id):
				if row.AlbumID not in albums:
					album = self.get_album_with_id(row.AlbumID)
					albums[row.AlbumID] = album
				else:
					album = albums[row.AlbumID]
				track = Track(row, self.db,album)
				tracks.append(track)
				yield track

		dfr = task.coiterate(query_db())
		dfr.addCallback(lambda gen: tracks)
		return dfr
	'''

if __name__ == '__main__':
	db = BansheeDB('foo')
	db.start()

	print(db.say_hi())
	for c in db.get_children('/'):
		print c

	for c in db.get_children('album:4453'):
		print c

	for c in db.get_children('artist:83'):
		print c

	try:
		while True:
			pass
	except:
		db.stop()

