"""Content-adaptive embedding SIMULATORS (S-UNIWARD and HILL) for detector testing.

These do **not** carry a message. A real adaptive scheme hides bits with syndrome-trellis
codes so the receiver can decode them; here we only reproduce *where the image changes*,
which is all a steganalysis detector sees. This is the standard way the literature
generates adaptive stego images for experiments ("embedding simulator").

How it works (Holub, Fridrich & Denemark 2014; Li et al. 2014):

1. A **cost** ``rho`` says how detectable it is to change each pixel by +-1. Textured pixels
   are cheap, smooth ones are expensive.
2. Changes are drawn independently: pixel ``i`` goes +1 or -1 with probability
   ``p_i = exp(-lambda * rho_i) / (1 + 2 * exp(-lambda * rho_i))`` and stays the same
   otherwise. ``lambda`` is chosen so the total Shannon entropy of the change pattern equals
   the payload size, which is what an ideal coder achieves.

Randomness uses NumPy's generator because nothing here must be reproduced by a receiver;
the seed only makes offline experiments repeatable.

The costs follow the published formulas; they are written from the papers, not copied from
the reference code, so values are close to, not bit-identical with, the original Matlab.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.signal import fftconvolve

Scheme = Literal["suniward", "hill"]
SchemeName = Scheme  # public alias used by the dataset scripts
SCHEMES: tuple[Scheme, ...] = ("suniward", "hill")
SIMULATED_METHODS = {"suniward": "suniward_sim", "hill": "hill_sim"}

# Daubechies-8 low-pass (decomposition) filter: 16 taps, sum = sqrt(2), unit energy.
DB8_LOW = np.array(
    [
        -0.00011747678412476953,
        0.0006754494064505693,
        -0.00039174037337694705,
        -0.004870352993451574,
        0.008746094047405777,
        0.013981027917398282,
        -0.044088253930794755,
        -0.017369301001807547,
        0.12874742662047847,
        0.0004724845739132828,
        -0.2840155429615469,
        -0.015829105256349306,
        0.5853546836542067,
        0.6756307362972898,
        0.31287159091429995,
        0.05441584224310401,
    ]
)
# Quadrature-mirror high-pass: g[n] = (-1)^n * h[N-1-n].
DB8_HIGH = DB8_LOW[::-1] * np.array([(-1.0) ** n for n in range(len(DB8_LOW))])

SIGMA_SUNIWARD = 2.0**-6  # stabiliser in the S-UNIWARD distortion (paper value)
WET_COST = 1e13  # cost of an impossible change (+1 on 255, -1 on 0)
HILL_KB = np.array([[-1.0, 2.0, -1.0], [2.0, -4.0, 2.0], [-1.0, 2.0, -1.0]])
MAX_BPP = 1.5  # entropy of a ternary change is at most log2(3) = 1.585 bits per pixel


def _padded_convolution(
    plane: NDArray[np.float64], kernel: NDArray[np.float64], pad: int
) -> NDArray[np.float64]:
    """Convolve with mirrored borders, returning an array of the original size."""
    padded = np.pad(plane, pad, mode="symmetric")
    result = fftconvolve(padded, kernel, mode="same")
    return np.asarray(result[pad:-pad, pad:-pad], dtype=np.float64)


def suniward_cost(cover: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Per-pixel S-UNIWARD cost of changing a pixel by +-1 (grayscale plane).

    Three directional wavelet filters (LH, HL, HH built from Daubechies-8) measure how much a
    change disturbs the image's high-frequency residuals, relative to how large those residuals
    already are. Disturbing a region that is already busy costs little.
    """
    plane = cover.astype(np.float64)
    kernels = (
        np.outer(DB8_LOW, DB8_HIGH),
        np.outer(DB8_HIGH, DB8_LOW),
        np.outer(DB8_HIGH, DB8_HIGH),
    )
    pad = 16
    cost = np.zeros_like(plane)
    for kernel in kernels:
        residual = _padded_convolution(plane, kernel, pad)
        inverse = 1.0 / (SIGMA_SUNIWARD + np.abs(residual))
        # Changing pixel (i, j) shifts each residual by +-kernel(u - i, v - j), so the cost is the
        # inverse-residual map correlated with |kernel|, i.e. convolved with its flipped copy.
        cost += _padded_convolution(inverse, np.abs(kernel)[::-1, ::-1], pad)
    return cost


def hill_cost(cover: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Per-pixel HILL cost: a high-pass filter finds texture, two low-pass filters spread it.

    Pixels in smooth regions get a large cost; the final 15x15 average makes costs spatially
    coherent so changes cluster in textured regions.
    """
    plane = cover.astype(np.float64)
    residual = np.abs(_padded_convolution(plane, HILL_KB, 2))
    smoothed = _padded_convolution(residual, np.full((3, 3), 1.0 / 9.0), 2)
    inverse = 1.0 / (smoothed + 1e-10)
    return _padded_convolution(inverse, np.full((15, 15), 1.0 / 225.0), 8)


def _wet_adjusted(
    cost: NDArray[np.float64], cover: NDArray[np.uint8]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Costs for +1 and -1, with impossible moves (past 0 or 255) made prohibitive."""
    plus, minus = cost.copy(), cost.copy()
    plus[cover == 255] = WET_COST
    minus[cover == 0] = WET_COST
    return plus, minus


def change_probabilities(
    plus: NDArray[np.float64], minus: NDArray[np.float64], lam: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Probability of +1 and -1 for every pixel at Lagrange multiplier ``lam``."""
    # Subtract the smaller exponent argument first so very large costs cannot overflow.
    ep, em = np.exp(-lam * plus), np.exp(-lam * minus)
    total = 1.0 + ep + em
    return ep / total, em / total


def ternary_entropy_bits(p_plus: NDArray[np.float64], p_minus: NDArray[np.float64]) -> float:
    """Total Shannon entropy (bits) of independent {-1, 0, +1} changes."""
    p_zero = 1.0 - p_plus - p_minus
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = [np.where(p > 0, -p * np.log2(p), 0.0) for p in (p_plus, p_minus, p_zero)]
    return float(sum(term.sum() for term in terms))


def solve_lambda(
    plus: NDArray[np.float64], minus: NDArray[np.float64], payload_bits: float
) -> float:
    """Find ``lambda`` whose change entropy equals the payload (entropy falls as lambda grows)."""
    low, high = 1e-12, 1.0
    for _ in range(80):  # grow the bracket until the entropy at ``high`` is below the target
        p_plus, p_minus = change_probabilities(plus, minus, high)
        if ternary_entropy_bits(p_plus, p_minus) <= payload_bits:
            break
        high *= 2.0
    for _ in range(80):  # bisect on a log scale
        middle = float(np.sqrt(low * high))
        p_plus, p_minus = change_probabilities(plus, minus, middle)
        if ternary_entropy_bits(p_plus, p_minus) > payload_bits:
            low = middle
        else:
            high = middle
    return float(np.sqrt(low * high))


def _simulate_plane(
    plane: NDArray[np.uint8], payload_bpp: float, scheme: Scheme, rng: np.random.Generator
) -> NDArray[np.uint8]:
    """Simulate embedding in one 2-D plane."""
    cost = suniward_cost(plane) if scheme == "suniward" else hill_cost(plane)
    plus, minus = _wet_adjusted(cost, plane)
    lam = solve_lambda(plus, minus, payload_bpp * plane.size)
    p_plus, p_minus = change_probabilities(plus, minus, lam)
    draw = rng.random(plane.shape)
    step = np.where(draw < p_plus, 1, np.where(draw < p_plus + p_minus, -1, 0))
    return np.clip(plane.astype(np.int16) + step, 0, 255).astype(np.uint8)


def simulate_embedding(
    cover: NDArray[np.uint8], payload_bpp: float, scheme: Scheme, seed: int = 1337
) -> NDArray[np.uint8]:
    """Return a simulated stego image carrying ``payload_bpp`` bits per pixel (per channel).

    Args:
        cover: Grayscale ``(H, W)`` or RGB ``(H, W, 3)`` uint8 image.
        payload_bpp: Payload in bits per pixel, between 0 (exclusive) and 1.5.
        scheme: ``"suniward"`` or ``"hill"``.
        seed: Seed for the random draw (offline experiments only).

    Returns:
        A new image of the same shape in which every sample changed by at most 1.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"Unknown scheme: {scheme!r}.")
    if cover.dtype != np.uint8 or cover.ndim not in (2, 3):
        raise ValueError("Cover must be a uint8 grayscale or RGB array.")
    if not 0.0 < payload_bpp <= MAX_BPP:
        raise ValueError(f"Payload must be in (0, {MAX_BPP}] bits per pixel.")
    rng = np.random.default_rng(seed)
    if cover.ndim == 2:
        return _simulate_plane(cover, payload_bpp, scheme, rng)
    channels = [_simulate_plane(cover[:, :, c], payload_bpp, scheme, rng) for c in range(3)]
    return np.stack(channels, axis=-1)
