"""Deterministic ChaCha20-derived sample permutations for keyed embedding."""

import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from numpy.typing import NDArray

from app.core.crypto.kdf import derive_key_argon2id
from app.core.stego.keystream import chacha20_keystream

MAX_PERMUTATION_SAMPLES = 4_000_000
STEGO_DOMAIN = b"stegaguard/stego/v1"
STEGO_HKDF_INFO = b"sg-stego-v1"


def derive_stego_keys(passphrase: str, stego_salt: bytes) -> tuple[bytes, bytes]:
    """Derive position and whitening keys from the shared passphrase and salt."""
    if len(stego_salt) != 16:
        raise ValueError("Stego salt must be exactly 16 bytes.")
    salt = hashes.Hash(hashes.SHA256())
    salt.update(STEGO_DOMAIN)
    argon_salt = salt.finalize()[:16]
    stego_key = derive_key_argon2id(passphrase, argon_salt)
    return expand_stego_key(stego_key, stego_salt)


def expand_stego_key(stego_key: bytes, stego_salt: bytes) -> tuple[bytes, bytes]:
    """Expand a 32-byte stego key into the position key and the whitening key.

    This is the cheap second half of ``derive_stego_keys``. Offline training
    data generation calls it directly with a random key so that it does not pay
    for one memory-hard Argon2id run per image; a uniformly random 32-byte key
    has exactly the distribution Argon2id's output is meant to have, so the
    embedded patterns are statistically identical. Live communication always
    goes through ``derive_stego_keys``.
    """
    if len(stego_key) != 32:
        raise ValueError("Stego key must be exactly 32 bytes.")
    if len(stego_salt) != 16:
        raise ValueError("Stego salt must be exactly 16 bytes.")
    keys = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=stego_salt,
        info=STEGO_HKDF_INFO,
    ).derive(stego_key)
    return keys[:32], keys[32:]


def permutation(key: bytes, sample_count: int) -> NDArray[np.int64]:
    """Return a stable permutation derived solely from ChaCha20.

    The stable argsort makes even the astronomically unlikely random-value tie
    deterministic across sender and receiver.
    """
    if len(key) != 32:
        raise ValueError("Position key must be exactly 32 bytes.")
    if sample_count < 0 or sample_count > MAX_PERMUTATION_SAMPLES:
        raise ValueError(f"Sample count must be between 0 and {MAX_PERMUTATION_SAMPLES}.")
    if sample_count == 0:
        return np.empty(0, dtype=np.int64)

    random_values = chacha20_keystream(key, sample_count * 8)
    values = np.frombuffer(random_values, dtype="<u8")
    return np.argsort(values, kind="stable")
