# Copyright 2009 Klas Lindberg <klas.lindberg@gmail.com>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.

class IR:
	SLEEP       = 1988737095
	POWER       = 1988706495
	HARD_POWER  = 63232
	REWIND      = 1988739135
	PAUSE       = 1988698335
	FORWARD     = 1988730975
	ADD         = 1988714655
	PLAY        = 1988694255
	UP          = 1988747295
	LEFT        = 1988726895
	RIGHT       = 1988743215
	DOWN        = 1988735055
	VOLUME_DOWN = 1988690175
	VOLUME_UP   = 1988722815
	NUM_0       = 1988728935
	NUM_1       = 1988751375
	NUM_2       = 1988692215
	NUM_3       = 1988724855
	NUM_4       = 1988708535
	NUM_5       = 1988741175
	NUM_6       = 1988700375
	NUM_7       = 1988733015
	NUM_8       = 1988716695
	NUM_9       = 1988749335
	FAVORITES   = 1988696295
	SEARCH      = 1988712615
	BROWSE      = 1988718735
	SHUFFLE     = 1988745255
	REPEAT      = 1988704455
	NOW_PLAYING = 1988720775
	SIZE        = 1988753415
	BRIGHTNESS  = 1988691195

	codes_debug = {
		SLEEP      :'SLEEP',
		POWER      :'POWER',
		HARD_POWER :'HARD POWER DOWN?',
		REWIND     :'REWIND',
		PAUSE      :'PAUSE',
		FORWARD    :'FORWARD',
		ADD        :'ADD',
		PLAY       :'PLAY',
		UP         :'UP',
		LEFT       :'LEFT',
		RIGHT      :'RIGHT',
		DOWN       :'DOWN',
		VOLUME_DOWN:'VOLUME DOWN',
		VOLUME_UP  :'VOLUME UP',
		NUM_0      :'0',
		NUM_1      :'1',
		NUM_2      :'2',
		NUM_3      :'3',
		NUM_4      :'4',
		NUM_5      :'5',
		NUM_6      :'6',
		NUM_7      :'7',
		NUM_8      :'8',
		NUM_9      :'9',
		FAVORITES  :'FAVORITES',
		SEARCH     :'SEARCH',
		BROWSE     :'BROWSE',
		SHUFFLE    :'SHUFFLE',
		REPEAT     :'REPEAT',
		NOW_PLAYING:'NOW PLAYING',
		SIZE       :'SIZE',
		BRIGHTNESS :'BRIGHTNESS'
	}
