"""Stable per-channel statistical and SPAM-lite image feature extraction."""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.steganalysis.classical.chi_square import chi_square_attack
from app.steganalysis.classical.rs import RSResult, rs_analysis
from app.steganalysis.classical.spa import sample_pair_analysis

BASE_FEATURE_NAMES = (
    "chi_square_statistic",
    "chi_square_log_p_value",
    "pair_difference",
    "rs_estimate",
    "spa_estimate",
    "rs_r_m",
    "rs_s_m",
    "rs_r_neg_m",
    "rs_s_neg_m",
    "lsb_ones_ratio_deviation",
    "lsb_entropy",
    "lsb_horizontal_agreement",
    "lsb_vertical_agreement",
)
SPAM_BINS = 7**3
CHANNEL_FEATURE_NAMES = BASE_FEATURE_NAMES + tuple(
    f"spam_{index:03d}" for index in range(SPAM_BINS)
)
FEATURE_NAMES = tuple(
    f"{aggregation}_{name}"
    for aggregation in ("mean", "min", "max")
    for name in CHANNEL_FEATURE_NAMES
)


@dataclass(frozen=True)
class ChannelFeatures:
    """Feature vector and detector intermediates for one grayscale channel."""

    values: NDArray[np.float64]
    names: tuple[str, ...]


def extract_features(image: NDArray[np.uint8]) -> NDArray[np.float32]:
    """Extract mean/min/max per-channel features with a stable finite schema.

    The vector includes Westfeld–Pfitzmann chi-square, Fridrich et al. RS,
    Dumitrescu et al. SPA, LSB-plane statistics, and 343 SPAM-lite joint bins
    inspired by Pevný, Bas & Fridrich (2010).

    Args:
        image: A 2-D grayscale or 3-D RGB uint8 image.

    Returns:
        Finite float32 vector whose names are ``FEATURE_NAMES``.
    """
    channels = _validate_image(image)
    channel_vectors = np.stack([_channel_features(channel).values for channel in channels])
    aggregated = np.concatenate(
        (
            channel_vectors.mean(axis=0),
            channel_vectors.min(axis=0),
            channel_vectors.max(axis=0),
        )
    )
    cleaned: NDArray[np.float32] = np.nan_to_num(
        aggregated, nan=0.0, posinf=0.0, neginf=0.0
    ).astype(np.float32)
    return cleaned


def channel_detector_features(channel: NDArray[np.uint8]) -> dict[str, float | int]:
    """Return interpretable detector estimates for the statistical fallback."""
    chi = chi_square_attack(channel)
    rs_result = rs_analysis(channel)
    spa = sample_pair_analysis(channel)
    return {
        "chi_square_statistic": chi.statistic,
        "chi_square_degrees_of_freedom": chi.degrees_of_freedom,
        "chi_square_p_value": chi.p_value,
        "pair_difference": chi.pair_difference,
        "rs_estimate": rs_result.estimated_rate,
        "spa_estimate": spa.estimated_rate,
        "rs_r_m": rs_result.r_m,
        "rs_s_m": rs_result.s_m,
        "rs_r_neg_m": rs_result.r_neg_m,
        "rs_s_neg_m": rs_result.s_neg_m,
    }


def statistical_fallback(image: NDArray[np.uint8]) -> dict[str, object]:
    """Return a labelled untrained heuristic based on chi-square, RS, and SPA.

    The arithmetic combination is a transparent educational fallback, not a
    calibrated classifier. It must not be presented as a trained model.
    """
    channels = _validate_image(image)
    details = [channel_detector_features(channel) for channel in channels]
    channel_scores = [
        float(
            np.clip(
                (
                    float(item["chi_square_p_value"])
                    + float(item["rs_estimate"])
                    + float(item["spa_estimate"])
                )
                / 3.0,
                0.0,
                1.0,
            )
        )
        for item in details
    ]
    probability = float(np.mean(channel_scores))
    return {
        "model": "statistical (untrained)",
        "label": "suspected_stego" if probability >= 0.5 else "clean",
        "probability": probability,
        "detectors": {
            "chi_square": float(np.mean([float(item["chi_square_p_value"]) for item in details])),
            "rs": float(np.mean([float(item["rs_estimate"]) for item in details])),
            "spa": float(np.mean([float(item["spa_estimate"]) for item in details])),
        },
        "features": details,
    }


def _channel_features(channel: NDArray[np.uint8]) -> ChannelFeatures:
    """Compute one channel's named chi-square, RS, SPA, LSB, and SPAM-lite data."""
    chi = chi_square_attack(channel)
    rs_result: RSResult = rs_analysis(channel)
    spa = sample_pair_analysis(channel)
    lsb = channel & 1
    ones_ratio = float(lsb.mean())
    entropy = _binary_entropy(ones_ratio)
    horizontal = float(np.mean(lsb[:, 1:] == lsb[:, :-1])) if channel.shape[1] > 1 else 0.0
    vertical = float(np.mean(lsb[1:, :] == lsb[:-1, :])) if channel.shape[0] > 1 else 0.0
    base = np.asarray(
        (
            chi.statistic,
            np.log(max(chi.p_value, float(np.finfo(np.float64).tiny))),
            chi.pair_difference,
            rs_result.estimated_rate,
            spa.estimated_rate,
            rs_result.r_m,
            rs_result.s_m,
            rs_result.r_neg_m,
            rs_result.s_neg_m,
            abs(ones_ratio - 0.5),
            entropy,
            horizontal,
            vertical,
        ),
        dtype=np.float64,
    )
    spam = _spam_lite(channel)
    return ChannelFeatures(np.concatenate((base, spam)), CHANNEL_FEATURE_NAMES)


def _spam_lite(channel: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Build normalized 7³ joint histograms of clipped triples of differences."""
    normalized_histograms: list[NDArray[np.float64]] = []
    for axis in (0, 1):
        differences = np.diff(channel.astype(np.int16), axis=axis)
        if differences.shape[axis] < 3:
            continue
        triples = np.stack(
            (
                np.take(differences, range(differences.shape[axis] - 2), axis=axis),
                np.take(differences, range(1, differences.shape[axis] - 1), axis=axis),
                np.take(differences, range(2, differences.shape[axis]), axis=axis),
            ),
            axis=-1,
        )
        bins = np.clip(triples, -3, 3) + 3
        indices = np.ravel_multi_index(bins.reshape(-1, 3).T, (7, 7, 7))
        histogram = np.bincount(indices, minlength=SPAM_BINS).astype(np.float64)
        if histogram.sum():
            histogram /= histogram.sum()
        normalized_histograms.append(histogram)
    if not normalized_histograms:
        return np.zeros(SPAM_BINS, dtype=np.float64)
    averaged: NDArray[np.float64] = np.mean(normalized_histograms, axis=0)
    return averaged


def _binary_entropy(probability: float) -> float:
    """Compute Shannon entropy for a Bernoulli bit distribution."""
    if probability <= 0 or probability >= 1:
        return 0.0
    return float(-probability * np.log2(probability) - (1 - probability) * np.log2(1 - probability))


def _validate_image(image: NDArray[np.uint8]) -> list[NDArray[np.uint8]]:
    """Validate grayscale/RGB shape and return channel views."""
    if image.dtype != np.uint8:
        raise ValueError("Image must use uint8 samples.")
    if image.ndim == 2 and image.size:
        return [image]
    if image.ndim == 3 and image.shape[2] == 3 and image.size:
        return [image[:, :, index] for index in range(3)]
    raise ValueError("Image must be a non-empty grayscale or RGB array.")
