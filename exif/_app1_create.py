"""Utility to create empty APP1 metadata bytes."""

from plum.int.big import UInt16

from exif._constants import ATTRIBUTE_ID_MAP, ExifMarkers
from exif._datatypes import ExifType, Ifd, IfdTag, TiffByteOrder, TiffHeader


def generate_empty_app1_bytes():
    """Generate an empty APP1 segment with IFDs 0, EXIF, and GPS.

    :returns: big endian APP1 segment with 3 IFDs
    :rtype: bytes

    """
    header_bytes = bytearray(ExifMarkers.APP1)
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

    # pylint: disable=unsubscriptable-object
    ifd0.tags[0].value_offset = tiff_header.nbytes + ifd0.nbytes  # IFD 0 --> EXIF
    ifd0.tags[1].value_offset = tiff_header.nbytes + ifd0.nbytes + exif_ifd.nbytes  # IFD 0 --> GPS
    # pylint: enable=unsubscriptable-object

    body_bytes = bytearray(tiff_header.pack())
    body_bytes += ifd0.pack()
    body_bytes += exif_ifd.pack()
    body_bytes += gps_ifd.pack()

    # Adjust the APP1 length (2 bytes ino header).
    UInt16(len(header_bytes + body_bytes)).pack_into(header_bytes, offset=2)

    return header_bytes + body_bytes
