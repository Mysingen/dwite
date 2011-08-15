import ctypes
import ctypes.util

SEARCH_FOR_METADATA   = 0x0
END_OF_STREAM         = 0x4
WRITE_STATUS_CONTINUE = 0x0

class FlacDecoder(object):
	decoder = None
	path    = None

	def __del__(self):
		self.__decoder_delete(self.decoder)
		pass

	def __init__(self, path):
		self.__load_libflac()
		self.decoder = self.__decoder_new()
		self.path    = path

		def write_callback(decoder, frame, buf, user):
			print 'write_callback()'
			return WRITE_STATUS_CONTINUE

		def error_callback(decoder, status, user):
			print 'error_callback()'

		# IMPORTANT: the callbacks must be saved somewhere to prevent the
		# garbage collector from smoking them (which leads to segfaults if
		# the calls are ever made)
		self.cb1 = self.__write_callback_type(write_callback)
		self.cb3 = self.__error_callback_type(error_callback)

		state = self.__init_file(
			self.decoder, self.path, self.cb1, None, self.cb3, self.path
		)
		if state != SEARCH_FOR_METADATA:
			raise Exception('decoder_init_file() failed')

	def __load_libflac(self):
		path = ctypes.util.find_library('FLAC')
		if path:
			self.libflac = ctypes.CDLL(path)
		if not self.libflac or not self.libflac._name:
			raise ImportError('failed to find libFLAC. Check your installation')

		#### define prototypes for all library functions we need ###############
		self.__decoder_new = self.libflac.FLAC__stream_decoder_new
		self.__decoder_new.restype = ctypes.c_void_p
		self.__decoder_new.params = []

		self.__decoder_delete = self.libflac.FLAC__stream_decoder_delete
		self.__decoder_delete.restype = None
		self.__decoder_delete.params = [ctypes.c_void_p]

		self.__init_file = self.libflac.FLAC__stream_decoder_init_file
		self.__init_file.restype = ctypes.c_int
		self.__init_file.params = [
			ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p,
			ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
		]

		self.__get_state = self.libflac.FLAC__stream_decoder_get_state
		self.__get_state.restype = ctypes.c_int
		self.__get_state.params = [ctypes.c_void_p]

		self.__get_state_string = \
			self.libflac.FLAC__stream_decoder_get_resolved_state_string
		self.__get_state_string.restype = ctypes.c_char_p
		self.__get_state_string.params = [ctypes.c_void_p]

		self.__skip_metadata = \
			self.libflac.FLAC__stream_decoder_process_until_end_of_metadata
		self.__skip_metadata.restype = ctypes.c_bool
		self.__skip_metadata.params = [ctypes.c_void_p]

		self.__skip_frame = self.libflac.FLAC__stream_decoder_skip_single_frame
		self.__skip_frame.restype = ctypes.c_bool
		self.__skip_frame.params = [ctypes.c_void_p]

		self.__get_position = \
			self.libflac.FLAC__stream_decoder_get_decode_position
		self.__get_position.restype = ctypes.c_bool
		self.__get_position.params = [ctypes.c_void_p, ctypes.c_void_p]

		self.__write_callback_type = ctypes.CFUNCTYPE(
			ctypes.c_int,
			ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
		)

		self.__error_callback_type = ctypes.CFUNCTYPE(
			None,
			ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p
		)
		#### end of prototypes #################################################

	def get_state(self):
		return self.__get_state(self.decoder)

	def get_state_string(self):
		return self.__get_state_string(self.decoder)

	def skip_metadata(self):
		return self.__skip_metadata(self.decoder)

	def skip_frame(self):
		return self.__skip_frame(self.decoder)

	def get_position(self):
		position = ctypes.c_int()
		self.__get_position(self.decoder, ctypes.byref(position))
		return position.value

