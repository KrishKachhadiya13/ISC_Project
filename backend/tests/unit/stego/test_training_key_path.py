"""The offline-training key path must match the live path where it matters."""

import hashlib

import numpy as np
import pytest

from app.core.crypto.kdf import derive_key_argon2id
from app.core.stego.embed import embed
from app.core.stego.extract import extract
from app.core.stego.scatter import STEGO_DOMAIN, derive_stego_keys, expand_stego_key

SALT = bytes(range(16))


def _cover(seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, (64, 64), dtype=np.uint8)


def test_derive_stego_keys_is_argon2_then_expand() -> None:
    """The refactor must not change the live derivation: Argon2id, then HKDF."""
    argon_salt = hashlib.sha256(STEGO_DOMAIN).digest()[:16]
    stego_key = derive_key_argon2id("a long enough passphrase", argon_salt)
    assert derive_stego_keys("a long enough passphrase", SALT) == expand_stego_key(stego_key, SALT)


def test_expand_validates_lengths() -> None:
    """Keys and salts have fixed sizes."""
    with pytest.raises(ValueError, match="32 bytes"):
        expand_stego_key(b"short", SALT)
    with pytest.raises(ValueError, match="16 bytes"):
        expand_stego_key(bytes(32), b"salt")


def test_expanded_keys_are_distinct_and_deterministic() -> None:
    """Position and whitening keys differ, and the same inputs give the same keys."""
    position, whitening = expand_stego_key(bytes(32), SALT)
    assert position != whitening
    assert (position, whitening) == expand_stego_key(bytes(32), SALT)
    assert expand_stego_key(b"\x01" * 32, SALT)[0] != position


def test_stego_key_embedding_is_deterministic_and_key_dependent() -> None:
    """Same key and salt give the same image; a different key scatters differently."""
    cover, payload = _cover(), b"offline training payload"
    one = embed(cover, payload, stego_key=b"\x01" * 32, stego_salt=SALT)
    again = embed(cover, payload, stego_key=b"\x01" * 32, stego_salt=SALT)
    other = embed(cover, payload, stego_key=b"\x02" * 32, stego_salt=SALT)
    assert np.array_equal(one, again)
    assert not np.array_equal(one, other)


def test_stego_key_embedding_changes_only_lsbs_for_replacement() -> None:
    """LSB replacement never touches the upper seven bits, on either key path."""
    cover = _cover(3)
    stego = embed(cover, b"x" * 200, stego_key=b"\x07" * 32, stego_salt=SALT)
    assert np.array_equal(cover >> 1, stego >> 1)
    assert np.count_nonzero(cover != stego) > 0


def test_stego_key_path_matches_passphrase_path_statistically() -> None:
    """Both paths flip about half of the embedded bits, spread over the whole image."""
    cover, payload = _cover(5), bytes(range(256)) + bytes(range(200))  # 456 B of 483 B capacity
    fast = embed(cover, payload, stego_key=b"\x09" * 32, stego_salt=SALT)
    live = embed(cover, payload, stego_passphrase="a long enough passphrase", stego_salt=SALT)
    for stego in (fast, live):
        changed = cover != stego
        embedded_bits = (len(payload) + 13) * 8
        assert 0.4 < np.count_nonzero(changed) / embedded_bits < 0.6
        rows = changed.reshape(64, 64).sum(axis=1)
        assert rows.min() > 0  # scattered, not confined to the top rows


def test_live_path_still_round_trips() -> None:
    """The passphrase path is unchanged: embed then extract recovers the payload."""
    cover, payload = _cover(7), b"live message"
    stego = embed(cover, payload, stego_passphrase="a long enough passphrase")
    assert extract(stego, stego_passphrase="a long enough passphrase") == payload


def test_keyed_mode_still_requires_a_passphrase_or_key() -> None:
    """Neither a passphrase nor a key is an error, as before."""
    with pytest.raises(ValueError, match="passphrase"):
        embed(_cover(), b"x")
