import os
import ctypes
import ctypes.util

# load the library
libflac = ctypes.CDLL(os.path.join(
	os.environ['DWITE_HOME'], 'lib', 'libFLAC.dylib'
))
if not libflac or not libflac._name:
	raise ImportError('failed to find libFLAC. Check your installation')

# define prototypes for all library functions we need
class prototype(object):
	new = libflac.FLAC__stream_decoder_new
	new.restype = ctypes.c_void_p
	new.params = []

	delete = libflac.FLAC__stream_decoder_delete
	delete.restype = None
	delete.params = [ctypes.c_void_p]

	init_file = libflac.FLAC__stream_decoder_init_file
	init_file.restype = ctypes.c_int
	init_file.params = [
		ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p,
		ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
	]

	get_state = libflac.FLAC__stream_decoder_get_state
	get_state.restype = ctypes.c_int
	get_state.params = [ctypes.c_void_p]

	get_state_string = \
		libflac.FLAC__stream_decoder_get_resolved_state_string
	get_state_string.restype = ctypes.c_char_p
	get_state_string.params = [ctypes.c_void_p]

	skip_metadata = libflac.FLAC__stream_decoder_process_until_end_of_metadata
	skip_metadata.restype = ctypes.c_bool
	skip_metadata.params = [ctypes.c_void_p]

	skip_frame = libflac.FLAC__stream_decoder_skip_single_frame
	skip_frame.restype = ctypes.c_bool
	skip_frame.params = [ctypes.c_void_p]

	get_position = libflac.FLAC__stream_decoder_get_decode_position
	get_position.restype = ctypes.c_bool
	get_position.params = [ctypes.c_void_p, ctypes.c_void_p]

write_callback_type = ctypes.CFUNCTYPE(
	ctypes.c_int,
	ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)

metadata_callback_type = ctypes.CFUNCTYPE(
	None,
	ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
)

error_callback_type = ctypes.CFUNCTYPE(
	None,
	ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
)

def write_callback(decoder, frame, buf, user):
	print 'write_callback()'
	return FlacDecoder.WRITE_STATUS_CONTINUE

def metadata_callback(decoder, metadata, user):
	pass

def error_callback(decoder, status, user):
	print 'error_callback()'

class FlacDecoder(object):
	SEARCH_FOR_METADATA   = 0x0
	END_OF_STREAM         = 0x4
	WRITE_STATUS_CONTINUE = 0x0

	decoder = None

	def __del__(self):
		prototype.delete(self.decoder)

	def __init__(self, path):
		self.decoder = prototype.new()

		# IMPORTANT: the callbacks must be saved somewhere to prevent the
		# garbage collector from smoking them (which leads to segfaults if
		# the calls are ever made)
		self.cb1 = write_callback_type(write_callback)
		self.cb2 = metadata_callback_type(metadata_callback)
		self.cb3 = error_callback_type(error_callback)

		state = prototype.init_file(
			self.decoder, path, self.cb1, self.cb2, self.cb3, None
		)
		if state != FlacDecoder.SEARCH_FOR_METADATA:
			raise Exception('decoder_init_file() failed')

	def get_state(self):
		return prototype.get_state(self.decoder)

	def get_state_string(self):
		return prototype.get_state_string(self.decoder)

	def skip_metadata(self):
		return prototype.skip_metadata(self.decoder)

	def skip_frame(self):
		return prototype.skip_frame(self.decoder)

	def get_position(self):
		position = ctypes.c_int()
		prototype.get_position(self.decoder, ctypes.byref(position))
		return position.value



