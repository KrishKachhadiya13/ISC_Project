"""GET /api/results and /api/results/plots/{name} — saved evaluation outputs only."""

import json
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.errors import ApiError
from app.config import settings

router = APIRouter(tags=["Results"])
# Plot names are restricted so a request can never reach outside results/plots.
_PLOT_NAME = re.compile(r"^[a-z0-9_]{1,80}\.png$")


@router.get("/results")
async def get_results() -> dict[str, Any]:
    """Return ``results/metrics.json`` exactly as the evaluation script wrote it.

    The UI shows only these numbers. If evaluation has not been run, the
    response is MODEL_UNAVAILABLE rather than placeholder values.
    """
    path = settings.RESULTS_DIR / "metrics.json"
    if not path.is_file():
        raise ApiError(
            "MODEL_UNAVAILABLE",
            "No evaluation results yet. Run `make eval` to create results/metrics.json.",
        )
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiError("INTERNAL", "results/metrics.json could not be read.") from exc
    return data


@router.get("/results/plots", response_model=list[str])
async def list_plots() -> list[str]:
    """List available plot images."""
    directory = settings.RESULTS_DIR / "plots"
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if _PLOT_NAME.fullmatch(path.name))


@router.get("/results/plots/{name}", response_class=FileResponse)
async def get_plot(name: str) -> FileResponse:
    """Serve one evaluation plot PNG."""
    path = settings.RESULTS_DIR / "plots" / name
    if not _PLOT_NAME.fullmatch(name) or not path.is_file():
        raise ApiError("NOT_FOUND", "Plot not found.")
    return FileResponse(path, media_type="image/png")
