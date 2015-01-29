import math, binascii

from liteeth.common import *
from liteeth.mac.common import *
from liteeth.test.common import *

def print_mac(s):
	print_with_prefix(s, "[MAC]")

preamble = split_bytes(eth_preamble, 8)

def crc32(l):
	crc = []
	crc_bytes = split_bytes(binascii.crc32(bytes(l)), 4)
	for byte in crc_bytes:
		crc.append(int(byte))
	return crc

# MAC model
class MACPacket(Packet):
	def __init__(self, init=[]):
		Packet.__init__(self, init)
		self.preamble_error = False
		self.crc_error = False

	def check_remove_preamble(self):
		if comp(self[0:8], preamble):
			for i in range(8):
				self.pop(0)
			return False
		else:
			return True

	def check_remove_crc(self):
		if comp(self[-4:], crc32(self[:-4])):
			for i in range(4):
				self.pop()
			return False
		else:
			return True

	def decode_remove_header(self):
		header = []
		for byte in self[:mac_header_len]:
			header.append(self.pop(0))
		for k, v in sorted(mac_header.items()):
			setattr(self, k, get_field_data(v, header))

	def decode(self):
		self.preamble_error = self.check_remove_preamble()
		self.crc_error = self.check_remove_crc()
		if self.crc_error or self.preamble_error:
			raise ValueError # XXX handle this properly
		else:
			self.decode_remove_header()

	def encode_header(self):
		header = 0
		for k, v in sorted(mac_header.items()):
			header |= (getattr(self, k) << (v.byte*8+v.offset))
		for d in reversed(split_bytes(header, mac_header_len)):
			self.insert(0, d)

	def insert_crc(self):
		for d in crc32(self):
			self.append(d)

	def insert_preamble(self):
		for d in reversed(preamble):
			self.insert(0, d)

	def encode(self):
		self.encode_header()
		self.insert_crc()
		self.insert_preamble()

	def __repr__(self):
		r = "--------\n"
		for k in sorted(mac_header.keys()):
			r += k + " : 0x%x" %getattr(self,k) + "\n"
		r += "payload: "
		for d in self:
			r += "%02x" %d
		return r

class MAC(Module):
	def  __init__(self, phy, debug=False, loopback=False):
		self.phy = phy
		self.debug = debug
		self.loopback = loopback
		self.tx_packets = []
		self.tx_packet = MACPacket()
		self.rx_packet = MACPacket()

		self.ip_callback = None
		self.arp_callback = None

	def set_ip_callback(self, callback):
		self.ip_callback = callback

	def set_arp_callback(self, callback):
		self.arp_callback = callback

	def send(self, packet):
		if self.debug:
			print_mac(">>>>>>>>")
			print_mac(packet)
		packet.encode()
		self.tx_packets.append(packet)

	def callback(self, datas):
		packet = MACPacket(datas)
		packet.decode()
		if self.debug:
			print_mac("<<<<<<<<")
			print_mac(packet)
		if self.loopback:
			self.send(packet)
		else:
			if self.ethernet_type == ethernet_type_ip:
				if self.ip_callback is not None:
					self.ip_callback(packet)
			elif self.ethernet_type == ethernet_type_arp:
				if self.arp_callback is not None:
					self.arp_callback(packet)
			else:
				raise ValueError # XXX handle this properly

	def gen_simulation(self, selfp):
		self.tx_packet.done = True
		while True:
			yield from self.phy.receive()
			self.callback(self.phy.packet)
			# XXX add full duplex
			if len(self.tx_packets) != 0:
				tx_packet = self.tx_packets.pop(0)
				yield from self.phy.send(tx_packet)
