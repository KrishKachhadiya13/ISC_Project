"""Pydantic request/response models; they also generate the OpenAPI docs."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """Inner part of the uniform error envelope."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """``{"error": {...}}`` returned by every failing request."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """Service status and the trained models currently loaded."""

    status: str
    version: str
    models_loaded: list[str]


class KeyGenerateRequest(BaseModel):
    """Password that will encrypt the exported private key."""

    key_password: str = Field(min_length=1, max_length=1024)


class KeyGenerateResponse(BaseModel):
    """A new Ed25519 keypair; the server keeps no copy."""

    public_key_pem: str
    private_key_pem_encrypted: str
    fingerprint: str
    fingerprint_short: str


class EmbedMetrics(BaseModel):
    """Image-quality and capacity figures for one embedding."""

    mse: float
    psnr: float
    ssim: float
    bpp: float
    bits_changed_pct: float
    capacity_bits: int
    used_bits: int


class EmbedResponse(BaseModel):
    """Stego PNG (base64 of the exact bytes), signed manifest, and metrics."""

    stego_png_base64: str
    manifest: dict[str, Any]
    metrics: EmbedMetrics
    diff_png_base64: str
    warnings: list[str]
    sender_fingerprint: str


class Stage(BaseModel):
    """One receiver-pipeline stage."""

    name: str
    status: Literal["passed", "failed", "skipped"]
    detail: str
    code: str | None = None


class ExtractResponse(BaseModel):
    """Ordered stages; content appears only when every stage passed."""

    stages: list[Stage]
    verified: bool
    plaintext: str | None = None
    file_base64: str | None = None
    filename: str | None = None
    technique: Literal["lsb", "lsb2", "stc"] | None = Field(
        default=None, description="Decoder used (null if extraction failed)."
    )
    mode: Literal["keyed", "sequential"] | None = Field(
        default=None, description="Placement mode that worked (null if nothing was recovered)."
    )
    supplied_key_fingerprint: str


class CheckResult(BaseModel):
    """Outcome of one independent integrity check."""

    ok: bool | None
    detail: str


class VerifyChecks(BaseModel):
    """The three checks of Section 6.6."""

    pixel_hash: CheckResult
    manifest_signature: CheckResult
    payload_signature: CheckResult | None


class VerifyResponse(BaseModel):
    """Per-check results and the overall decision."""

    checks: VerifyChecks
    overall_ok: bool


class DetectResponse(BaseModel):
    """Verdict, per-detector breakdown, features, and optional heatmaps."""

    label: Literal["clean", "suspected_stego"]
    probability: float
    threshold: float
    operating_point: str
    decision_source: str
    detectors: dict[str, dict[str, Any]]
    features: dict[str, float]
    heatmap_gradcam_png_base64: str | None = None
    heatmap_residual_png_base64: str | None = None
    warnings: list[str]
    latency_ms: float
    image_sha256: str
    width: int
    height: int
    channels: int


class BatchItem(BaseModel):
    """One file's detection result, or the error that stopped it."""

    filename: str
    result: DetectResponse | None = None
    error: ErrorBody | None = None


class BatchResponse(BaseModel):
    """Results in upload order."""

    items: list[BatchItem]


class ModelInfo(BaseModel):
    """Registered model metadata, without bulky lists."""

    name: str
    loaded: bool
    metadata: dict[str, Any]


class ModelsResponse(BaseModel):
    """Every discovered model plus detectors that are not trained yet."""

    models: list[ModelInfo]
    detectors: dict[str, dict[str, Any]]
    load_warnings: list[str]
    ensemble: dict[str, Any] | None
