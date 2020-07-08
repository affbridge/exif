"""Test adding EXIF attributes."""

import binascii
import os
import textwrap
import unittest

from exif import Image
from exif.tests.add_exif_baselines.add_short import ADD_SHORT_BASELINE, ADD_SHORT_LE_BASELINE
from exif.tests.test_little_endian import read_attributes as read_attributes_little_endian
from exif.tests.test_read_exif import read_attributes_florida_beach

# pylint: disable=protected-access


class TestAddExif(unittest.TestCase):

    """Test cases for adding EXIF attributes."""

    def setUp(self):
        """Open sample image file in binary mode for use in test cases."""
        florida = os.path.join(os.path.dirname(__file__), 'florida_beach.jpg')
        little_endian = os.path.join(os.path.dirname(__file__), 'little_endian.jpg')
        self.image = Image(florida)
        self.image_le = Image(little_endian)

        assert self.image.has_exif
        assert self.image_le.has_exif

    def test_add_shorts(self):
        """Test adding two new SHORT tags to an image."""
        self.image.light_source = 1
        self.image.contrast = 0

        assert self.image.light_source == 1
        assert self.image.contrast == 0

        # Verify pre-existing attributes can still be read as expected.
        for attribute, func, value in read_attributes_florida_beach:
            assert func(getattr(self.image, attribute)) == value

        segment_hex = binascii.hexlify(self.image._segments['APP1'].get_segment_bytes()).decode("utf-8").upper()
        self.assertEqual('\n'.join(textwrap.wrap(segment_hex, 90)),
                         ADD_SHORT_BASELINE)

    def test_add_shorts_le(self):
        """Test adding two new SHORT tags to a little endian image."""
        self.image_le.contrast = 1
        self.image_le.light_source = 24

        assert self.image_le.light_source == 24
        assert self.image_le.contrast == 1

        # Verify pre-existing attributes can still be read as expected.
        for attribute, func, value in read_attributes_little_endian:
            assert func(getattr(self.image_le, attribute)) == value

        segment_hex = binascii.hexlify(self.image_le._segments['APP1'].get_segment_bytes()).decode("utf-8").upper()
        self.assertEqual('\n'.join(textwrap.wrap(segment_hex, 90)),
                         ADD_SHORT_LE_BASELINE)
