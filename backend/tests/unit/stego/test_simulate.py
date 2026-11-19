"""Adaptive embedding simulators: filters, costs, entropy matching, and adaptivity."""

import numpy as np
import pytest

from app.core.stego.simulate import (
    DB8_HIGH,
    DB8_LOW,
    SCHEMES,
    _wet_adjusted,
    change_probabilities,
    hill_cost,
    simulate_embedding,
    solve_lambda,
    suniward_cost,
    ternary_entropy_bits,
)


def _textured_right_flat_left(size: int = 96, seed: int = 0) -> np.ndarray:
    """Left half perfectly flat, right half noisy: an adaptive scheme should avoid the left."""
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 128, dtype=np.uint8)
    image[:, size // 2 :] = rng.integers(60, 200, (size, size - size // 2), dtype=np.uint8)
    return image


def _photo_like(size: int = 128, seed: int = 1) -> np.ndarray:
    """Smooth gradients plus mild noise, a crude stand-in for a natural image."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    base = 128 + 60 * np.sin(x / 11) + 40 * np.cos(y / 17)
    return np.clip(base + rng.normal(0, 4, (size, size)), 0, 255).astype(np.uint8)


def test_db8_filters_are_a_valid_orthonormal_pair() -> None:
    """Guards against a mistyped coefficient: sum sqrt(2), unit energy, orthogonal shifts."""
    assert DB8_LOW.size == 16
    assert DB8_LOW.sum() == pytest.approx(np.sqrt(2))
    assert (DB8_LOW**2).sum() == pytest.approx(1.0)
    for shift in range(2, 16, 2):  # orthogonal to its own even shifts
        assert float(np.dot(DB8_LOW[:-shift], DB8_LOW[shift:])) == pytest.approx(0.0, abs=1e-12)
    assert DB8_HIGH.sum() == pytest.approx(0.0, abs=1e-12)  # a high-pass has no DC response
    assert (DB8_HIGH**2).sum() == pytest.approx(1.0)
    assert float(np.dot(DB8_LOW, DB8_HIGH)) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("cost_function", [suniward_cost, hill_cost])
def test_costs_are_positive_finite_and_cheaper_in_texture(cost_function) -> None:  # type: ignore[no-untyped-def]
    """Texture must be cheaper to change than flat regions."""
    image = _textured_right_flat_left()
    cost = cost_function(image)
    assert cost.shape == image.shape and np.isfinite(cost).all() and (cost > 0).all()
    assert cost[:, 60:90].mean() < cost[:, 5:35].mean()


def test_wet_pixels_cannot_move_out_of_range() -> None:
    """255 cannot go up and 0 cannot go down."""
    image = np.array([[0, 128], [255, 128]], dtype=np.uint8)
    plus, minus = _wet_adjusted(np.ones((2, 2)), image)
    assert plus[1, 0] > 1e12 and minus[0, 0] > 1e12
    assert plus[0, 0] == 1.0 and minus[1, 0] == 1.0


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("bpp", [0.05, 0.2, 0.5, 1.0])
def test_entropy_matches_the_requested_payload(scheme: str, bpp: float) -> None:
    """The solved lambda makes the change entropy equal the payload, as an ideal coder would."""
    image = _photo_like()
    cost = suniward_cost(image) if scheme == "suniward" else hill_cost(image)
    plus, minus = _wet_adjusted(cost, image)
    lam = solve_lambda(plus, minus, bpp * image.size)
    entropy = ternary_entropy_bits(*change_probabilities(plus, minus, lam))
    assert entropy == pytest.approx(bpp * image.size, rel=0.01)


@pytest.mark.parametrize("scheme", SCHEMES)
def test_simulated_stego_changes_by_at_most_one_and_stays_in_range(scheme: str) -> None:
    """Every changed sample differs by exactly 1, even on saturated pixels."""
    image = _photo_like()
    image[:8, :8] = 0
    image[-8:, -8:] = 255
    stego = simulate_embedding(image, 0.4, scheme)  # type: ignore[arg-type]
    delta = stego.astype(int) - image.astype(int)
    assert set(np.unique(delta).tolist()) <= {-1, 0, 1}
    assert stego.dtype == np.uint8 and stego.shape == image.shape
    assert (delta[:8, :8] >= 0).all() and (delta[-8:, -8:] <= 0).all()


@pytest.mark.parametrize("scheme", SCHEMES)
def test_changes_concentrate_in_textured_regions(scheme: str) -> None:
    """The defining property of adaptive embedding."""
    image = _textured_right_flat_left()
    changed = simulate_embedding(image, 0.3, scheme) != image  # type: ignore[arg-type]
    right, left = changed[:, 48:].sum(), changed[:, :48].sum()
    assert right > 0 and left < 0.1 * right


@pytest.mark.parametrize("scheme", SCHEMES)
def test_more_payload_changes_more_pixels_and_seed_controls_randomness(scheme: str) -> None:
    """Monotone in payload; deterministic per seed; different seeds differ."""
    image = _photo_like()
    low = (simulate_embedding(image, 0.1, scheme) != image).sum()  # type: ignore[arg-type]
    high = (simulate_embedding(image, 0.8, scheme) != image).sum()  # type: ignore[arg-type]
    assert high > 3 * low
    first = simulate_embedding(image, 0.3, scheme, seed=1)  # type: ignore[arg-type]
    assert np.array_equal(first, simulate_embedding(image, 0.3, scheme, seed=1))  # type: ignore[arg-type]
    assert not np.array_equal(first, simulate_embedding(image, 0.3, scheme, seed=2))  # type: ignore[arg-type]


def test_rgb_input_and_argument_validation() -> None:
    """RGB is processed per channel; impossible requests are rejected."""
    rgb = np.stack([_photo_like(64, seed=s) for s in range(3)], axis=-1)
    assert simulate_embedding(rgb, 0.2, "hill").shape == rgb.shape
    gray = _photo_like(64)
    with pytest.raises(ValueError, match="Unknown scheme"):
        simulate_embedding(gray, 0.2, "wow")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Payload"):
        simulate_embedding(gray, 2.0, "hill")
    with pytest.raises(ValueError, match="Payload"):
        simulate_embedding(gray, 0.0, "hill")
    with pytest.raises(ValueError, match="uint8"):
        simulate_embedding(gray.astype(np.float32), 0.2, "hill")  # type: ignore[arg-type]
