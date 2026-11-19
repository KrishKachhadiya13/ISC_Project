"""Discovery of complete, versioned steganalysis model artifacts."""

import json
from dataclasses import dataclass
from pathlib import Path

MODEL_ARTIFACTS = {
    "classical_rf": ".joblib",
    "classical_hgb": ".joblib",
    "cnn_v1": ".pt",
}


@dataclass(frozen=True)
class RegisteredModel:
    """A model artifact paired with its validated JSON metadata."""

    name: str
    artifact_path: Path
    metadata_path: Path
    metadata: dict[str, object]


def discover_models(models_dir: Path) -> tuple[RegisteredModel, ...]:
    """Discover complete supported model/sidecar pairs in a model directory.

    Missing directories are valid for installations without trained models.
    A present sidecar or weight file without its counterpart is an explicit
    artifact error, rather than a silently registered partial model.
    """
    directory = Path(models_dir)
    if not directory.exists():
        return ()
    if not directory.is_dir():
        raise NotADirectoryError(f"Model path is not a directory: {directory}")

    models: list[RegisteredModel] = []
    for name, suffix in MODEL_ARTIFACTS.items():
        metadata_path = directory / f"{name}.json"
        artifact_path = directory / f"{name}{suffix}"
        if not metadata_path.exists() and not artifact_path.exists():
            continue
        if not metadata_path.is_file():
            raise FileNotFoundError(f"Model metadata is missing: {metadata_path}")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact is missing: {artifact_path}")
        metadata = _read_metadata(metadata_path, name)
        models.append(
            RegisteredModel(
                name=name,
                artifact_path=artifact_path,
                metadata_path=metadata_path,
                metadata=metadata,
            )
        )
    return tuple(models)


def _read_metadata(path: Path, expected_name: str) -> dict[str, object]:
    """Read a JSON sidecar and confirm it describes the expected model."""
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read model metadata {path}: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ValueError(f"Model metadata must be a JSON object: {path}")
    if metadata.get("model") != expected_name:
        raise ValueError(f"Model metadata {path} must identify {expected_name!r}.")
    return metadata
