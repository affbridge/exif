"""Utility to create empty APP1 metadata bytes."""

from plum import unpack_from

from plum.int.big import UInt16

from exif._add_tag_utils import value_fits_in_ifd_tag
from exif._constants import ATTRIBUTE_ID_MAP, ATTRIBUTE_NAME_MAP, ATTRIBUTE_TYPE_MAP, ERROR_IMG_NO_ATTR, ExifMarkers
from exif._datatypes import ExifType, Ifd, IfdTag, TiffByteOrder, TiffHeader
from exif.ifd_tag import (
    Ascii, BaseIfdTag, Byte, ExifVersion, Long, Rational, Short, Slong, Srational, UserComment, WindowsXp)
from exif.ifd_tag._rational import RationalDtype


def generate_empty_app1_bytes():
    header_bytes = ExifMarkers.APP1
    header_bytes += b"\x00\x00"  # APP1 length (touched up later at end)
    header_bytes += b"\x45\x78\x69\x66\x00\x00" # EXIF word, NULL, and padding

    tiff_header = TiffHeader(byte_order=TiffByteOrder.BIG, reserved=0x2A, ifd_offset=0x8)

    default_tags = [
        # Note: These pointers are touched up later.
        IfdTag(tag_id=ATTRIBUTE_ID_MAP["_exif_ifd_pointer"], type=ExifType.LONG, value_count=1, value_offset=0),
        IfdTag(tag_id=ATTRIBUTE_ID_MAP["_gps_ifd_pointer"], type=ExifType.LONG, value_count=1, value_offset=0),
    ]
    ifd0 = Ifd(tags=default_tags, next=0)  # leave pointer to IFD 1 as 0 since there isn't a thumbnail

    exif_ifd = Ifd(tags=[], next=0)
    gps_ifd = Ifd(tags=[], next=0)

    ifd0.tags[0].value_offset = tiff_header.nbytes + ifd0.nbytes  # IFD 0 --> EXIF
    ifd0.tags[1].value_offset = tiff_header.nbytes + ifd0.nbytes + exif_ifd.nbytes  # IFD 0 --> GPS

    body_bytes = tiff_header.pack()
    body_bytes += ifd0.pack()
    body_bytes += exif_ifd.pack()
    body_bytes += gps_ifd.pack()

    app1_len = UInt16.view(header_bytes, offset=2)  # 2 bytes into the header, i.e., right after the marker
    app1_len = len(header_bytes + body_bytes)  # TODO: Verify that this is header and body too and not just body

    return header_bytes + body_bytes
