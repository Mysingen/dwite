import struct

# PIL dependencies
import Image
import ImageDraw

class Canvas:
	bitmap   = ''    # Suitable for output to SqueezeBox with the 'grfe' command
	image    = None  # private member
	drawable = None  # an ImageDraw object for others to interact with
	size     = None  # pixel size of the drawable. tuple (x,y)

	# the full SqueezeBox display is divided into stripes. depending on what is
	# to be done, it should be thought of either as 320 vertical stripes of 1x32,
	# or 4 horizontal stripes of 320x8. the vertical stripes are used to put bits
	# on the wire, while the horizontal are used for device specific compositing.
	# neither is a useful concept for "artistic" compositing. for that we keep a
	# PIL drawable that some other class can render content onto.

	def __init__(self, size):
		self.size     = size
		self.image    = Image.new('1', size, 0)
		self.drawable = ImageDraw.Draw(self.image)

	def clear(self):
		self.drawable.rectangle((0,0,self.size[0],self.size[1]), fill=0)
	
	def prepare_transmission(self):
		# SqueezeBox expects each 8 bit part of each vertical stripe to be sent
		# in big endian bit order. unfortunately, this conflicts with the natural
		# traverse order of drawables, but we can easily prepare the entire image
		# for the transmission by transposing the horizontal stripes.
		for y in [8, 16, 24, 32]:
			box = (0, y-8, self.size[0], y)
			sub = self.image.crop(box).transpose(Image.FLIP_TOP_BOTTOM)
			self.image.paste(sub, box)

		# pack each vertical stripe into unsigned 32 bit integers
		pack = []
		data = list(self.image.getdata()) # len() == x*y
		for i in range(self.size[0]):
			stripe = 0
			for j in range(self.size[1]):
				stripe = stripe | (data[j * self.size[0] + i] << j)
			pack.append(struct.pack('L', stripe))

		self.bitmap = ''.join(pack) # ready for transmission
