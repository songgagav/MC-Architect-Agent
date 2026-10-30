"""Typed failures for the local reference library."""


class LibraryError(ValueError):
    """Base class for invalid library data or operations."""


class LibraryLookupError(LibraryError):
    """A requested reference, style, module, region, or rule is not registered."""


class AssetIntegrityError(LibraryError):
    """A reference file is absent, corrupt, changed, or structurally unsupported."""


class LitematicFormatError(AssetIntegrityError):
    """A Litematic NBT file does not satisfy the supported structural format."""
