"""APP1 metadata interface module for EXIF tags."""

from plum import unpack_from

from plum.int.big import UInt16

from exif._add_tag_utils import value_fits_in_ifd_tag
from exif._constants import ATTRIBUTE_ID_MAP, ATTRIBUTE_NAME_MAP, ATTRIBUTE_TYPE_MAP, ERROR_IMG_NO_ATTR, ExifMarkers
from exif._datatypes import ExifType, ExifTypeLe, Ifd, IfdLe, IfdTag, IfdTagLe, TiffByteOrder, TiffHeader
from exif.ifd_tag import (
    Ascii, BaseIfdTag, Byte, ExifVersion, Long, Rational, Short, Slong, Srational, UserComment, WindowsXp)
from exif.ifd_tag._rational import RationalDtype


class App1MetaData:

    """APP1 metadata interface class for EXIF tags."""

    def _add_empty_ifd(self, ifd):
        if not ifd == "gps":
            raise RuntimeError("only can add GPS IFD to image, not {0}".format(ifd))

        if 1 not in self.ifd_pointers:
            raise RuntimeError("can't yet add to images without a subsequent IFD 1")

        if self.endianness == TiffByteOrder.BIG:
            exif_type_cls = ExifType
            ifd_cls = Ifd
            ifd_tag_cls = IfdTag
        else:
            exif_type_cls = ExifTypeLe
            ifd_cls = IfdLe
            ifd_tag_cls = IfdTagLe

        new_app1_bytes = self.body_bytes[:self.ifd_pointers[1]]
        bytes_after_new_ifd = self.body_bytes[self.ifd_pointers[1]:]

        # Inert empty IFD.
        empty_ifd = Ifd(tags=[], next=0)
        new_app1_bytes += empty_ifd.pack()

        # Touch up pointer to IFD 1 (which we already know exists).
        ifd_zero = unpack_from(ifd_cls, new_app1_bytes, offset=self.ifd_pointers[0])
        ifd_zero.next += empty_ifd.nbytes
        ifd_zero.pack_into(new_app1_bytes, offset=self.ifd_pointers[0])

        # Touch up IFD 1 pointers!
        ifd1 = unpack_from(ifd_cls, bytes_after_new_ifd, offset=0)
        for tag_index in range(ifd1.count):
            tag_t = ifd1.tags[tag_index]
            is_value_in_ifd_tag_itself = value_fits_in_ifd_tag(tag_t, exif_type_cls)
            if tag_t.tag_id in [ATTRIBUTE_ID_MAP["jpeg_interchange_format"]] or not is_value_in_ifd_tag_itself:
                tag_t.value_offset += empty_ifd.nbytes
            ifd1.tags[tag_index] = tag_t
        ifd1.pack_into(bytes_after_new_ifd, offset=0)

        # Parse new bytes containing the additional placeholder IFD.
        self.body_bytes = new_app1_bytes + bytes_after_new_ifd
        self._parse_ifd_segments()

        # Adjust the size of the APP1 header to reflect the new length.
        app1_len = UInt16.view(self.header_bytes, offset=2)  # 2 bytes into the header, i.e., right after the marker
        app1_len += empty_ifd.nbytes

        # Add pointer tag to IFD 0.
        offset_of_new_ifd = self.ifd_pointers[1]  # IFD 1 is pushed back to after the new IFD tag that takes its place
        self._add_tag("_gps_ifd_pointer", offset_of_new_ifd)

    def _add_tag(self, tag, value):
        try:
            tag_type, ifd_number = ATTRIBUTE_TYPE_MAP[tag]
        except KeyError:
            raise AttributeError("cannot add attribute {0} to image".format(tag))

        if self.endianness == TiffByteOrder.BIG:
            exif_type_cls = ExifType
            ifd_cls = Ifd
            ifd_tag_cls = IfdTag
        else:
            exif_type_cls = ExifTypeLe
            ifd_cls = IfdLe
            ifd_tag_cls = IfdTagLe

        if ifd_number not in self.ifd_pointers:
            self._add_empty_ifd(ifd_number)

        # Make a list of all IFDs that will need to be re-packed with touched up pointers.
        subsequent_ifd_names = [ifd for ifd, offset in self.ifd_pointers.items()
                                if offset > self.ifd_pointers[ifd_number]]
        subsequent_ifd_offsets = sorted([offset for offset in self.ifd_pointers.values()
                                         if offset > self.ifd_pointers[ifd_number]])

        # Determine the number of bytes that will be injected.
        added_bytes = ifd_tag_cls.nbytes
        pointer_value_bytes = 0
        value_count = 1

        if tag_type == exif_type_cls.ASCII and len(value) >= 4:
            pointer_value_bytes = len(value) + 1  # add one for null termination

        if tag_type == exif_type_cls.ASCII:
            value_count = len(value) + 1

        if tag_type == exif_type_cls.RATIONAL:
            if isinstance(value, tuple):
                value_count = len(value)
            else:
                value_count = 1

            pointer_value_bytes = value_count * RationalDtype.nbytes

        added_bytes += pointer_value_bytes
        # TODO: Support other types after finishing and testing ASCII (e.g., GPS especially)

        # Keep all bytes prior to the IFD where the new tag will be added.
        new_app1_bytes = self.body_bytes[:self.ifd_pointers[ifd_number]]

        # If IFD 1 occurs after that added tag, adjust the pointer to it from IFD 0.
        if ifd_number != 0:
            ifd_zero = unpack_from(ifd_cls, new_app1_bytes, offset=self.ifd_pointers[0])
            if ifd_zero.next and 1 in subsequent_ifd_names:
                ifd_zero.next += added_bytes

            # Also adjust the pointers to the GPS and EXIF IFDs if they occur after the added tag.
            for tag_index in range(ifd_zero.count):
                tag_t = ifd_zero.tags[tag_index]

                is_ifd_pointer_to_adjust = (tag_t.tag_id == ATTRIBUTE_ID_MAP["_gps_ifd_pointer"]
                                            and "gps" in subsequent_ifd_names)
                is_ifd_pointer_to_adjust |= (tag_t.tag_id == ATTRIBUTE_ID_MAP["_exif_ifd_pointer"]
                                             and "exif" in subsequent_ifd_names)

                if is_ifd_pointer_to_adjust:
                    tag_t.value_offset += added_bytes

                ifd_zero.tags[tag_index] = tag_t

            ifd_zero.pack_into(new_app1_bytes, offset=self.ifd_pointers[0])

        # Unpack the original bytes of the IFD to which the new tag will be added to.
        target_ifd_offset = self.ifd_pointers[ifd_number]
        target_ifd = unpack_from(ifd_cls, self.body_bytes, offset=target_ifd_offset)

        if subsequent_ifd_offsets:
            orig_ifd_values = self.body_bytes[target_ifd_offset + target_ifd.nbytes:subsequent_ifd_offsets[0]]
        else:
            orig_ifd_values = self.body_bytes[target_ifd_offset + target_ifd.nbytes:]

        # Determine if a pointer to a value is necessary, and if so, find it.
        if (tag_type == exif_type_cls.ASCII and len(value) >= 4) or tag_type == exif_type_cls.RATIONAL:
            if subsequent_ifd_offsets:
                value_pointer = subsequent_ifd_offsets[0] + ifd_tag_cls.nbytes
            else:
                # Can put at end since if EXIF or GPS is the last IFD, there must not be a thumbnail and IFD 1.
                value_pointer = len(self.body_bytes) + ifd_tag_cls.nbytes
        elif tag == "_gps_ifd_pointer":  # must set pointer values now or else they'll incorrectly point to 0x00 when parsing
            value_pointer = value
        else:
            value_pointer = 0

        # Iterate over the IFD's tags and increase any value offset pointers by the size of an IFD tag.
        for tag_index in range(target_ifd.count):
            tag_t = target_ifd.tags[tag_index]

            is_ifd_pointer_to_adjust = (tag_t.tag_id == ATTRIBUTE_ID_MAP["_gps_ifd_pointer"]
                                        and "gps" in subsequent_ifd_names)
            is_ifd_pointer_to_adjust |= (tag_t.tag_id == ATTRIBUTE_ID_MAP["_exif_ifd_pointer"]
                                         and "exif" in subsequent_ifd_names)

            is_value_in_ifd_tag_itself = value_fits_in_ifd_tag(tag_t, exif_type_cls)
            if is_ifd_pointer_to_adjust:
                tag_t.value_offset += added_bytes
            elif not is_value_in_ifd_tag_itself:
                tag_t.value_offset += ifd_tag_cls.nbytes

            target_ifd.tags[tag_index] = tag_t

        # Add the new tag to the IFD.
        target_ifd.count += 1
        target_ifd.tags.append(ifd_tag_cls(
            tag_id=ATTRIBUTE_ID_MAP[tag], type=tag_type, value_count=value_count, value_offset=value_pointer))

        # If necessary, touch up the pointer to the next IFD.
        if target_ifd.next:
            target_ifd.next += added_bytes

        # Pack new IFD bytes into the new body bytes (along with the pre-existing values that follow).
        target_ifd.pack_into(new_app1_bytes, offset=target_ifd_offset)
        new_app1_bytes += orig_ifd_values
        new_app1_bytes += b"\x00" * pointer_value_bytes

        while subsequent_ifd_offsets:
            # TODO: Fix all this duplication
            current_ifd_offset = subsequent_ifd_offsets.pop(0)
            target_ifd = unpack_from(ifd_cls, self.body_bytes, offset=current_ifd_offset)

            if subsequent_ifd_offsets:
                orig_ifd_values = self.body_bytes[current_ifd_offset + target_ifd.nbytes:subsequent_ifd_offsets[0]]
            else:
                orig_ifd_values = self.body_bytes[current_ifd_offset + target_ifd.nbytes:]

            for tag_index in range(target_ifd.count):
                tag_t = target_ifd.tags[tag_index]
                is_value_in_ifd_tag_itself = value_fits_in_ifd_tag(tag_t, exif_type_cls)
                if tag_t.tag_id in [ATTRIBUTE_ID_MAP["jpeg_interchange_format"]] or not is_value_in_ifd_tag_itself:
                    tag_t.value_offset += added_bytes

                target_ifd.tags[tag_index] = tag_t

            if target_ifd.next:
                target_ifd.next += added_bytes

            new_app1_bytes += target_ifd.pack()
            new_app1_bytes += orig_ifd_values

        # Finally, adjust the size of the APP1 header to reflect the new length.
        app1_len = UInt16.view(self.header_bytes, offset=2)  # 2 bytes into the header, i.e., right after the marker
        app1_len += added_bytes

        # Reload to pick up on new bytes arrangement and then modify the currently-zero value.
        self.body_bytes = new_app1_bytes
        self._parse_ifd_segments()
        self.ifd_tags[ATTRIBUTE_ID_MAP[tag]].modify(value)

    def _delete_ifd_tag(self, attribute_id):
        # Overwrite pointer data with null bytes (if applicable, depending on datatype).
        self.ifd_tags[attribute_id].wipe()

        # Unpack the original IFD section.
        corresponding_ifd_offset = self.ifd_pointers[self.tag_parent_ifd[attribute_id]]
        if self.endianness == TiffByteOrder.BIG:
            ifd_cls = Ifd
        else:
            ifd_cls = IfdLe
        orig_ifd = unpack_from(ifd_cls, self.body_bytes, offset=corresponding_ifd_offset)

        # Construct a new IFD section datatype containing all tags but the deletion target.
        preserved_tags = [tag for tag in orig_ifd.tags if tag.tag_id != attribute_id]
        new_ifd = ifd_cls(tags=preserved_tags, next=orig_ifd.next)

        # Pack in new IFD bytes with null bytes (i.e., an empty IFD tag) appended to preserve pointers.
        # Note: The pack_into method overrides the pre-existing bytes.
        new_ifd.pack_into(self.body_bytes, offset=corresponding_ifd_offset)
        IfdTag(0, 0, 0, 0).pack_into(self.body_bytes, offset=corresponding_ifd_offset + new_ifd.nbytes)

        # Remove tag from parser tag dictionary.
        del self.ifd_tags[attribute_id]
        del self.tag_parent_ifd[attribute_id]

        # Regenerate information about existing tags.
        self._parse_ifd_segments()

    def _extract_thumbnail(self):  # TODO: Adjust this to use JPEGInterchangeFormat value.
        if 1 in self.ifd_pointers:  # IFD segment 1 contains thumbnail (if present)
            hex_after_ifd1 = self.body_bytes[self.ifd_pointers[1]:]
            try:
                start_index = hex_after_ifd1.index(ExifMarkers.SOI)
                end_index = hex_after_ifd1.index(ExifMarkers.EOI) + len(ExifMarkers.EOI)
            except ValueError:
                pass  # no thumbnail
            else:
                self.thumbnail_bytes = hex_after_ifd1[start_index:end_index]

    def get_segment_bytes(self):
        """Get equivalent APP1 segment bytes.

        :returns: segment bytes
        :rtype: bytes

        """
        return bytes(self.header_bytes) + bytes(self.body_bytes)

    def get_tag_list(self):
        """Get a list of EXIF tag attributes present in the image object.

        :returns: image EXIF tag names
        :rtype: list of str

        """
        return [ATTRIBUTE_NAME_MAP.get(key, "<unknown EXIF tag {0}>".format(key))
                for key in self.ifd_tags]

    def _iter_ifd_tags(self, ifd_key):
        ifd_offset = self.ifd_pointers[ifd_key]

        if self.endianness == TiffByteOrder.BIG:
            ifd_t = unpack_from(Ifd, self.body_bytes, offset=ifd_offset)
        else:
            ifd_t = unpack_from(IfdLe, self.body_bytes, offset=ifd_offset)

        for tag_index in range(ifd_t.count):
            tag_offset = ifd_offset + 2 + tag_index * IfdTag.nbytes  # count is 2 bytes
            tag_t = ifd_t.tags[tag_index]
            tag_py_ins = self._tag_factory(tag_t, tag_offset)

            if ifd_key != 1 or tag_t.tag_id not in self.ifd_tags:  # don't let thumbnail tags override base image tags
                self.ifd_tags[tag_t.tag_id] = tag_py_ins
                self.tag_parent_ifd[tag_t.tag_id] = ifd_key

            if tag_t.tag_id == ATTRIBUTE_ID_MAP["_exif_ifd_pointer"]:
                self.ifd_pointers["exif"] = tag_t.value_offset

            if tag_t.tag_id == ATTRIBUTE_ID_MAP["_gps_ifd_pointer"]:
                self.ifd_pointers["gps"] = tag_t.value_offset

        return ifd_t.next

    def _parse_ifd_segments(self):
        tiff_header = unpack_from(TiffHeader, self.body_bytes)
        self.endianness = tiff_header.byte_order

        current_ifd = 0
        current_ifd_offset = tiff_header.ifd_offset

        while current_ifd_offset:
            self.ifd_pointers[current_ifd] = current_ifd_offset
            current_ifd_offset = self._iter_ifd_tags(current_ifd)
            current_ifd += 1

        if "exif" in self.ifd_pointers:
            self._iter_ifd_tags("exif")

        if "gps" in self.ifd_pointers:
            self._iter_ifd_tags("gps")

    def _tag_factory(self, tag_t, offset):  # pylint: disable=too-many-branches
        if self.endianness == TiffByteOrder.BIG:
            exif_type_cls = ExifType
        else:
            exif_type_cls = ExifTypeLe

        if ATTRIBUTE_ID_MAP["xp_title"] <= tag_t.tag_id <= ATTRIBUTE_ID_MAP["xp_subject"]:  # legacy Windows XP tags
            cls = WindowsXp
        elif ATTRIBUTE_ID_MAP["exif_version"] == tag_t.tag_id:  # custom ASCII encoding without termination character
            cls = ExifVersion
        elif ATTRIBUTE_ID_MAP["user_comment"] == tag_t.tag_id:
            cls = UserComment
        elif tag_t.type == exif_type_cls.BYTE:
            cls = Byte
        elif tag_t.type == exif_type_cls.ASCII:
            cls = Ascii
        elif tag_t.type == exif_type_cls.SHORT:
            cls = Short
        elif tag_t.type == exif_type_cls.LONG:
            cls = Long
        elif tag_t.type == exif_type_cls.RATIONAL:
            cls = Rational
        elif tag_t.type == exif_type_cls.SLONG:
            cls = Slong
        elif tag_t.type == exif_type_cls.SRATIONAL:
            cls = Srational
        else:
            cls = BaseIfdTag

        return cls(offset, self)

    def __init__(self, segment_bytes):
        self.header_bytes = bytearray(segment_bytes[:0xA])
        self.body_bytes = bytearray(segment_bytes[0xA:])

        self.endianness = None
        self.ifd_pointers = {}
        self.ifd_tags = {}
        self.tag_parent_ifd = {}
        self.thumbnail_bytes = None

        self._parse_ifd_segments()
        self._extract_thumbnail()

    def __delattr__(self, item):
        try:
            # Determine if attribute is an IFD tag accessor.
            attribute_id = ATTRIBUTE_ID_MAP[item]
        except KeyError:  # pragma: no cover
            # Coverage and behavior tested by Image class.
            # Attribute is a class member. Delete natively.
            super(App1MetaData, self).__delattr__(item)
        else:
            # Attribute is not a class member. Delete EXIF tag value.
            try:
                self.ifd_tags[attribute_id]
            except KeyError:
                raise AttributeError(ERROR_IMG_NO_ATTR.format(item))

            self._delete_ifd_tag(attribute_id)

    def __getattr__(self, item):
        """If attribute is not a class member, get the value of the EXIF tag of the same name."""
        try:
            attribute_id = ATTRIBUTE_ID_MAP[item]
        except KeyError:
            raise AttributeError("unknown image attribute {0}".format(item))

        try:
            ifd_tag = self.ifd_tags[attribute_id]
        except KeyError:
            raise AttributeError(ERROR_IMG_NO_ATTR.format(item))

        return ifd_tag.read()

    def __setattr__(self, key, value):
        try:
            # Determine if attribute is an IFD tag accessor.
            attribute_id = ATTRIBUTE_ID_MAP[key]
        except KeyError:
            # Attribute is a class member. Set natively.
            super(App1MetaData, self).__setattr__(key, value)
        else:
            try:
                ifd_tag = self.ifd_tags[attribute_id]
            except KeyError:
                # Tag is not in image already.
                self._add_tag(key, value)
            else:
                try:
                    ifd_tag.modify(value)
                except ValueError as exec:  # e.g., if doesn't fit into tag, try deleting and re-adding
                    try:
                        exif_type = ATTRIBUTE_TYPE_MAP[key][0]
                    except KeyError:
                        raise exec

                    if self.endianness == TiffByteOrder.BIG:
                        exif_type_cls = ExifType
                    else:
                        exif_type_cls = ExifTypeLe

                    if exif_type == exif_type_cls.ASCII:
                        self._delete_ifd_tag(attribute_id)
                        self._add_tag(key, value)
                    else:
                        raise exec
