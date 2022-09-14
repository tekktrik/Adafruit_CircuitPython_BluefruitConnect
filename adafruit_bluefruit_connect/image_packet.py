# SPDX-FileCopyrightText: 2019 Dan Halbert for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""
`adafruit_bluefruit_connect.image_packet`
====================================================

Bluefruit Connect App image data packet.

* Author(s): Alec Delaney

"""

import struct
import displayio
import gc

from .packet import Packet


class ImagePacket(Packet):
    """A packet of information relating to an image"""

    _FMT_PARSE_META = "<xxBHH"
    # _FMT_CONSTRUCT_META doesn't include the trailing checksum byte.
    _FMT_CONSTRUCT_META = "<2sBHH"
    _TYPE_HEADER = b"!I"


    def __init__(self, colorspace, width, height, raw_pixels, *, bitmap_and_palette=None):
        self._colorspace = colorspace
        self._color_format = (
            "2B" if self.colorspace == displayio.Colorspace.RGB565 else "3B"
        )
        self._width = width
        self._height = height
        self._raw_pixels = raw_pixels
        if bitmap_and_palette is not None:
            self._bitmap = bitmap_and_palette[0]
            self._palette = bitmap_and_palette[1]
        else:
            self._parse_pixels(raw_pixels)

    @staticmethod
    def get_bytes_per_color(colorspace):
        return(
            2 if colorspace == displayio.Colorspace.RGB565 else 3
        )

    def to_bytes(self):
        """Return the bytes needed to send this packet"""
        partial_packet = struct.pack(
            self._FMT_CONSTRUCT_META,
            self._TYPE_HEADER,
            self._colorspace,
            self._width,
            self._height
        )
        partial_packet += self._raw_pixels
        return self.add_checksum(partial_packet)

    @property
    def colorspace(self):
        """The colorspace of the image as a `~displayio.Colorspace` value"""
        return (
            displayio.Colorspace.RGB565
            if self._colorspace == 16
            else displayio.Colorspace.RGB888
        )

    @property
    def width(self):
        """The width of the image, in pixels"""
        return self._width

    @property
    def height(self):
        """The height of the image, in pixels"""
        return self._height

    @property
    def bitmap(self):
        """The Bitmap object corresponding to the image"""
        return self._bitmap

    @property
    def palette(self):
        """The Palette object corresponding to the image"""
        return self._palette

    @classmethod
    def parse_private(cls, packet):
        """Construct an ImagePacket from an incoming packet.

        Do not call this directly; call Packet.from_bytes() instead.
        pylint makes it difficult to call this method _parse(), hence the name.
        """
        args = struct.unpack(cls._FMT_PARSE_META, packet[0:7])
        args += (packet[7:-1],)
        return cls(*args)

    def _parse_pixels(self, raw_pixels):
        """Parses the raw pixels into a corresponding bitmap and palette"""

        num_pixels = self._width * self._height

        # First iteration: find out how many unique pallete colors there are
        bitmap_colors = []
        for pixel_index in range(num_pixels):

            # Get slice of the bytes
            start_byte = pixel_index * 2
            end_byte = (
                start_byte + 2
                if self.colorspace == displayio.Colorspace.RGB565
                else start_byte + 3
            )
            #print("RAW::", raw_pixels[start_byte:end_byte])
            parsed_pixels = struct.unpack(
                self._color_format, raw_pixels[start_byte:end_byte]
            )
            palette_color = self._get_pixel_colors(parsed_pixels, self.colorspace)

            # Store color if needed
            if palette_color not in bitmap_colors:
                bitmap_colors.append(palette_color)

        gc.collect()

        # Second iteration: create Palette and Bitmap
        # Palette
        palette = displayio.Palette(len(bitmap_colors))
        bitmap = displayio.Bitmap(self._width, self._height, len(bitmap_colors))
        for index, color in enumerate(bitmap_colors):
            palette[index] = color

        # Bitmap
        for pixel_index in range(num_pixels):

            # Get slice of the bytes
            start_byte = pixel_index * 2
            end_byte = (
                start_byte + 2
                if self.colorspace == displayio.Colorspace.RGB565
                else start_byte + 3
            )
            parsed_pixels = struct.unpack(
                self._color_format, raw_pixels[start_byte:end_byte]
            )
            palette_color = self._get_pixel_colors(parsed_pixels)
            bitmap[pixel_index] = bitmap_colors.index(palette_color)

        # Store bitmap and palette
        self._bitmap = bitmap
        self._palette = palette

    def _get_pixel_colors(self, parsed_pixel, colorspace):
        """Convert pixel color to an integer (e.g., 0xFFFFFF)"""

        if colorspace == displayio.Colorspace.RGB565:
            full_color = 0
            current_index = 0
            for color_part in parsed_pixel:
                full_color |= (color_part << current_index)
            current_index += 8
            red_data = (0xF800 & full_color) >> 8
            green_data = (0x07E0 & full_color) >> 3
            blue_data = (0x001F & full_color) << 3
        else:
            blue_data, green_data, red_data = parsed_pixel
        return (red_data << 16) & (blue_data << 8) & green_data

    @classmethod
    def from_image(cls, bitmap: displayio.Bitmap, palette: displayio.Palette, *, colorspace: displayio.Colorspace = displayio.Colorspace.RGB565):

        is_565 = colorspace == displayio.Colorspace.RGB565
        bytes_per_color = 2 if is_565 else 3
        colorspace_value = 16 if is_565 else 24
        pixel_data = bytearray()
        color_list = []

        # Iterate over colors so conversions (if needed) only happen once
        for color in palette:
            if is_565:
                color_converter = displayio.ColorConverter()
                color = color_converter.convert(color)
            color_list.append(color)

        # Iterate to assemble pixel data
        color_index = 0
        print("in")
        while True:
            try:
                start_index = 0
                end_index = start_index + bytes_per_color
                new_data = struct.pack("I", bitmap[start_index:end_index])[:bytes_per_color]
                pixel_data += new_data
                print(new_data)
                color_index += 1
            except IndexError:
                break
        print("out")

        gc.collect()

        return cls(colorspace_value, bitmap.width, bitmap.height, pixel_data, bitmap_and_palette=(bitmap, palette))

# Register this class with the superclass. This allows the user to import only what is needed.
ImagePacket.register_packet_type()
