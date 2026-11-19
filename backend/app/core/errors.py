"""Map core exceptions to the stable error codes of the public API (Section 7).

This lives in ``core`` (not ``api``) so the receiver pipeline can label each
failed stage with a code without importing any web framework.
"""

from app.core.crypto.exceptions import (
    DecryptionFailedError,
    InvalidPacketError,
    KeyMismatchError,
    VerificationFailedError,
    WeakPasswordError,
)
from app.core.stego.exceptions import (
    CapacityExceededError,
    InvalidImageError,
    NoHiddenDataError,
    StcUnavailableError,
    UnsupportedImageError,
)

# Order matters only for readability; each exception class is distinct.
_CODE_BY_EXCEPTION: tuple[tuple[type[Exception], str], ...] = (
    (InvalidImageError, "INVALID_IMAGE"),
    (UnsupportedImageError, "UNSUPPORTED_FORMAT"),
    (CapacityExceededError, "CAPACITY_EXCEEDED"),
    (NoHiddenDataError, "NO_HIDDEN_DATA"),
    (StcUnavailableError, "STC_UNAVAILABLE"),
    (WeakPasswordError, "WEAK_PASSWORD"),
    (KeyMismatchError, "KEY_MISMATCH"),
    (VerificationFailedError, "VERIFICATION_FAILED"),
    (DecryptionFailedError, "DECRYPTION_FAILED"),
    # A packet whose stego header passed its CRC but whose structure is broken
    # has been corrupted or forged, so it is an integrity (verification) failure.
    (InvalidPacketError, "VERIFICATION_FAILED"),
)


def error_code_for(error: Exception) -> str:
    """Return the API error code for a core exception, or ``INTERNAL``.

    Args:
        error: Exception raised by a crypto or stego operation.

    Returns:
        One of the Section 7 error codes.
    """
    for exception_type, code in _CODE_BY_EXCEPTION:
        if isinstance(error, exception_type):
            return code
    return "INTERNAL"
