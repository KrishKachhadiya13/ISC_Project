"""Typed errors raised by image steganography operations."""


class StegoError(Exception):
    """Base class for steganography failures."""


class InvalidImageError(StegoError):
    """Raised when image bytes cannot be decoded as a supported image."""


class UnsupportedImageError(StegoError):
    """Raised when an image format or sample representation is unsupported."""


class CapacityExceededError(StegoError):
    """Raised when a payload does not fit in the cover image."""

    def __init__(self, maximum_payload_bytes: int) -> None:
        """Store the maximum payload size alongside a readable error."""
        self.maximum_payload_bytes = maximum_payload_bytes
        super().__init__(f"Payload exceeds capacity; maximum is {maximum_payload_bytes} bytes.")


class StcUnavailableError(StegoError):
    """The optional pystcstego package is not installed, so S-UNIWARD and HILL cannot embed."""


class NoHiddenDataError(StegoError):
    """Raised when a stream header is absent, invalid, or cannot be decoded."""
