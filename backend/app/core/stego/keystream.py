"""ChaCha20 keystream helpers for reproducible keyed stego operations."""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms


def chacha20_keystream(key: bytes, length: int, nonce: bytes = bytes(16)) -> bytes:
    """Generate ``length`` bytes of ChaCha20 keystream.

    Args:
        key: A 32-byte ChaCha20 key.
        length: Number of output bytes requested.
        nonce: The 16-byte nonce used by ``cryptography``'s ChaCha20 API.

    Returns:
        Deterministic keystream bytes.

    Raises:
        ValueError: If the key, nonce, or requested length is invalid.
    """
    if len(key) != 32:
        raise ValueError("ChaCha20 key must be exactly 32 bytes.")
    if len(nonce) != 16:
        raise ValueError("ChaCha20 nonce must be exactly 16 bytes.")
    if length < 0:
        raise ValueError("Keystream length must be non-negative.")
    if length == 0:
        return b""

    encryptor = Cipher(algorithms.ChaCha20(key, nonce), mode=None).encryptor()
    return encryptor.update(bytes(length)) + encryptor.finalize()
