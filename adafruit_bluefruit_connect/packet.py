# SPDX-FileCopyrightText: 2019 Dan Halbert for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_bluefruit_connect.packet`
====================================================

Bluefruit Connect App packet superclass

* Author(s): Dan Halbert for Adafruit Industries

"""

import struct
import time
import math

class Packet:
    """
    A Bluefruit app controller packet. A packet consists of these bytes, in order:

      - '!' - The first byte is always an exclamation point.
      - *type* - A single byte designating the type of packet: b'A', b'B', etc.
      - *data ...* - Multiple bytes of data, varying by packet type.
      - *checksum* - A single byte checksum, computed by adding up all the data
        bytes and inverting the sum.

    This is an abstract class.
    """

    # All concrete subclasses should define these class attributes. They're listed here
    # as a reminder and to make pylint happy.
    # _FMT_PARSE is the whole packet.
    _FMT_PARSE = None
    # In each class, set PACKET_LENGTH = struct.calcsize(_FMT_PARSE).
    PACKET_LENGTH = None
    # _FMT_CONSTRUCT does not include the trailing byte, which is the checksum.
    _FMT_CONSTRUCT = None
    # The first byte of the prefix is always b'!'. The second byte is the type code.
    _TYPE_HEADER = None

    _type_to_class = {}

    @classmethod
    def register_packet_type(cls):
        """Register a new packet type, using this class and its ``cls._TYPE_HEADER``.
        The ``from_bytes()`` and ``from_stream()`` methods will then be able
        to recognize this type of packet.
        """

        print("Ran register")
        print(cls)
        Packet._type_to_class[cls._TYPE_HEADER] = cls

    def to_bytes(self):
        raise NotImplementedError("Must be implemented in subclass")

    @classmethod
    def from_bytes(cls, packet):
        """Create an appropriate object of the correct class for the given packet bytes.
        Validate packet type, length, and checksum.
        """

        # pylint: disable=import-outside-toplevel
        from adafruit_bluefruit_connect.image_packet import ImagePacket

        if len(packet) < 3:
            raise ValueError("Packet too short")
        packet_class = cls._type_to_class.get(packet[0:2], None)
        if not packet_class:
            raise ValueError("Unregistered packet type {}".format(packet[0:2]))

        # In case this was called from a subclass, make sure the parsed
        # type matches up with the current class.
        if not issubclass(packet_class, cls):
            raise ValueError("Packet type is not a {}".format(cls.__name__))

        if (
            packet_class != ImagePacket
            and len(packet) != packet_class.PACKET_LENGTH
        ):
            print(packet_class)
            raise ValueError("Wrong length packet")

        #print(cls.checksum(packet[0:-1]))
        #print("100:", packet[500])
        #print(packet[-1])
        if cls.checksum(packet[0:-1]) != packet[-1]:
            raise ValueError("Bad checksum")

        # A packet class may do further validation of the data.
        return packet_class.parse_private(packet)


    def into_stream(self, stream, *, interleave_size=100):

        from adafruit_bluefruit_connect.image_packet import ImagePacket

        data = self.to_bytes()

        if isinstance(self, ImagePacket):
            stream.write(data[0:7])
            loop_count = math.ceil(len(data) / interleave_size)
            slice_start = 0
            for _ in range(loop_count):
                slice_end = slice_start + interleave_size
                stream.write(data[slice_start:slice_end])
                while stream.read(1) != b"\x06":
                    pass
        else:
            stream.write(data)
        

    @classmethod
    def from_stream(cls, stream, *, interleave_size=100):
        """Read the next packet from the incoming stream. Wait as long as the timeout
        set on stream, using its own preset timeout.
        Return None if there was no input, otherwise return an instance
        of one of the packet classes registered with ``Packet``.
        Raise an Error if the packet was not recognized or was malformed

        :param stream stream: an input stream that provides standard stream read operations,
          such as ``ble.UARTServer`` or ``busio.UART``.
        """

        from adafruit_bluefruit_connect.image_packet import ImagePacket

        # Loop looking for a b'!' packet start. If the buffer has overflowed,
        # or there's been some other problem, we may need to skip some characters
        # to get to a packet start.
        print("Ping!")
        while True:
            print(stream.in_waiting)
            start = stream.read(1)
            if not start:
                # Timeout: nothing read.
                return None
            else:
                print(start)

            #time.sleep(0.1)

            if start == b"!":
                print("Found packet start!")
                # Found start of packet.
                packet_type = stream.read(1)
                if not packet_type:
                    # Timeout: nothing more read.
                    return None
                break

            # Didn't find a packet start.
            raw_text_packet_cls = cls._type_to_class.get(b"RT", None)
            # Is RawTextPacket registered?
            # If so, read an entire line and pass that to RawTextPacket.
            if raw_text_packet_cls:
                packet = bytes(start + stream.readline())
                return raw_text_packet_cls(packet)

            # else loop and try again.

        header = bytes(start + packet_type)
        packet_class = cls._type_to_class.get(header, None)
        print("is get!")
        if not packet_class:
            raise ValueError("Unregistered packet type {}".format(header))
        # TODO: The following will need to be fixed because there is no
        # PACKET_LENGTH for ImagePacket yet
        if packet_class == ImagePacket:
            packet = header
            colorspace_byte = stream.read(1)
            colorspace_value = int.from_bytes(colorspace_byte, "little")
            bytes_per_pixel = 2 if colorspace_value == 16 else 3
            width_byte = stream.read(2)
            height_byte = stream.read(2)
            width_value = int.from_bytes(width_byte, "little")
            height_value = int.from_bytes(height_byte, "little")
            size_data = width_value * height_value * bytes_per_pixel + 1
            packet += colorspace_byte
            packet += width_byte
            packet += height_byte
            print("size_data:", size_data)
            print("colorspace:", colorspace_value)
            print("width:", width_value)
            print("height:", height_value)
            loop_count = math.ceil(size_data / interleave_size)
            for _ in range(loop_count):
                print("ping")
                stream.read(interleave_size)
                stream.write(b"\x06")
            packet += stream.read(size_data)
            packet += stream.read(1)
        else:
            packet = header + stream.read(packet_class.PACKET_LENGTH - 2)
        return cls.from_bytes(packet)

    @classmethod
    def parse_private(cls, packet):
        """Default implementation for subclasses.
        Assumes arguments to ``__init__()`` are exactly the values parsed using
        ``cls._FMT_PARSE``. Subclasses may need to reimplement if that assumption
        is not correct.

        Do not call this directly. It's called from ``cls.from_bytes()``.
        pylint makes it difficult to call this method _parse(), hence the name.
        """
        return cls(*struct.unpack(cls._FMT_PARSE, packet))

    @staticmethod
    def checksum(partial_packet):
        """Compute checksum for bytes, not including the checksum byte itself."""
        return ~sum(partial_packet) & 0xFF

    def add_checksum(self, partial_packet):
        """Compute the checksum of partial_packet and return a new bytes
        with the checksum appended.
        """
        return partial_packet + bytes((self.checksum(partial_packet),))
