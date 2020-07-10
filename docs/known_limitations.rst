#################
Known Limitations
#################

This package contains the following known limitations:

- Accessing SLONG tags is not supported (since no IFD tags in the EXIF
  specification are SLONG type).
- ASCII tags cannot be modified to a value longer than their original length.
- EXIF metadata cannot yet be added to an image without any pre-existing EXIF metadata.
- Modifying Windows XP tags is not supported.
