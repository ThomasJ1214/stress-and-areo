"""Errors raised by the OpenRocket importer."""


class OrkFormatError(ValueError):
    """The input is not a readable OpenRocket document (wrong format, corrupt, or unsafe)."""
