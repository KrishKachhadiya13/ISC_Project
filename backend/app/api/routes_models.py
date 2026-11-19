"""GET /api/models — which detectors exist, which are trained, and their metadata."""

from typing import Any

from fastapi import APIRouter, Request

from app.api.deps import get_suite
from app.api.schemas import ModelInfo, ModelsResponse

router = APIRouter(tags=["Models"])
# Long lists (1,068 feature names, per-cover IDs) are useful on disk, not in the UI.
_OMITTED_KEYS = {"feature_names", "splits", "cover_ids"}


def summarize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky lists from a model sidecar, keeping everything else."""
    return {key: value for key, value in metadata.items() if key not in _OMITTED_KEYS}


@router.get("/models", response_model=ModelsResponse)
async def list_models(request: Request) -> ModelsResponse:
    """List registered models and the status of each detector family."""
    suite = get_suite(request)
    loaded = set(suite.loaded_model_names())
    models = [
        ModelInfo(
            name=model.name,
            loaded=model.name in loaded,
            metadata=summarize_metadata(dict(model.metadata)),
        )
        for model in suite.registered
    ]
    detectors: dict[str, dict[str, Any]] = {
        "statistical": {"available": True, "trained": False, "model": "statistical (untrained)"},
        "rf": {
            "available": suite.classical is not None,
            "trained": suite.classical is not None,
            "model": suite.classical.name if suite.classical else None,
            "threshold": suite.classical.threshold if suite.classical else None,
        },
        "cnn": {
            "available": suite.cnn is not None,
            "trained": suite.cnn is not None,
            "model": "cnn_v1" if suite.cnn else None,
            "threshold": suite.cnn.threshold if suite.cnn else None,
        },
    }
    return ModelsResponse(
        models=models,
        detectors=detectors,
        load_warnings=suite.load_warnings,
        ensemble=suite.ensemble,
    )
