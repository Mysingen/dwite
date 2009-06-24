class IR:
	SLEEP       = 1203276150
	POWER       = 3208677750
	HARD_POWER  = 16187392
	REWIND      = 1069582710
	PAUSE       = 3743451510
	FORWARD     = 1604356470
	ADD         = 2673903990
	PLAY        = 4010838390
	UP          = 534808950
	LEFT        = 1871743350
	RIGHT       = 802195830
	DOWN        = 1336969590
	VOLUME_DOWN = 4278225270
	VOLUME_UP   = 2139130230
	NUM_0       = 1738049910
	NUM_1       = 267422070
	NUM_2       = 4144531830
	NUM_3       = 2005436790
	NUM_4       = 3074984310
	NUM_5       = 935889270
	NUM_6       = 3609758070
	NUM_7       = 1470663030
	NUM_8       = 2540210550
	NUM_9       = 401115510
	FAVORITES   = 3877144950
	SEARCH      = 0 # SEARCH button not reactive in emulator
	BROWSE      = 2406517110
	SHUFFLE     = 668502390
	REPEAT      = 3342371190
	NOW_PLAYING = 2272823670
	SIZE        = 133728630
	BRIGHTNESS  = 4211378550

class RemoteEvent:
	code   = -1 # valid values taken from the IR codes above
	stress = 0  # valid values >= 1
	
	def __init__(self, code, stress):
		self.code   = code
		self.stress = stress
