# API reference

StegaGuard API v0.1.0. Generated from the OpenAPI schema by `python -m scripts.export_api_docs`; live docs are at `/docs` when the backend runs.

All endpoints live under `/api`. Errors always use one envelope:

```json
{
  "error": {
    "code": "CAPACITY_EXCEEDED",
    "message": "…",
    "details": {}
  }
}
```

| Error code | HTTP status |
|---|---|
| `INVALID_IMAGE` | 400 |
| `UNSUPPORTED_FORMAT` | 415 |
| `IMAGE_TOO_LARGE` | 413 |
| `CAPACITY_EXCEEDED` | 422 |
| `WEAK_PASSWORD` | 422 |
| `BAD_KEY` | 400 |
| `KEY_MISMATCH` | 422 |
| `NO_HIDDEN_DATA` | 422 |
| `VERIFICATION_FAILED` | 422 |
| `DECRYPTION_FAILED` | 422 |
| `MODEL_UNAVAILABLE` | 503 |
| `RATE_LIMITED` | 429 |
| `BAD_REQUEST` | 400 |
| `NOT_FOUND` | 404 |
| `INTERNAL` | 500 |

Verification failures inside `/extract` are reported in a normal `200` response (see the stages list); input problems use the envelope above.

## `POST /api/detect`

**Detect Image**

Scan one image and explain the verdict.

Request body (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | `string` | yes | Any image to scan. |
| `detectors` | `string` | no | 'all' or CSV of statistical,rf,cnn. |
| `operating_point` | `"balanced" \| "low_false_alarm"` | no |  |
| `explain` | `boolean` | no | Return CNN heatmaps. |

Response `200` (`DetectResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `label` | `"clean" \| "suspected_stego"` | yes |  |
| `probability` | `number` | yes |  |
| `threshold` | `number` | yes |  |
| `operating_point` | `string` | yes |  |
| `decision_source` | `string` | yes |  |
| `detectors` | `object` | yes |  |
| `features` | `object` | yes |  |
| `heatmap_gradcam_png_base64` | `string \| null` | no |  |
| `heatmap_residual_png_base64` | `string \| null` | no |  |
| `warnings` | `string[]` | yes |  |
| `latency_ms` | `number` | yes |  |
| `image_sha256` | `string` | yes |  |
| `width` | `integer` | yes |  |
| `height` | `integer` | yes |  |
| `channels` | `integer` | yes |  |

Possible error statuses: `400`, `413`

## `POST /api/detect/batch`

**Detect Batch**

Scan several images without heatmaps; one bad file does not fail the batch.

Request body (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `images` | `string[]` | yes | Up to 20 images. |
| `detectors` | `string` | no |  |
| `operating_point` | `"balanced" \| "low_false_alarm"` | no |  |

Response `200` (`BatchResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `items` | `BatchItem[]` | yes |  |

Possible error statuses: `400`, `413`

## `POST /api/embed`

**Embed Message**

Run the sender pipeline entirely in memory and return the exact PNG bytes.

Request body (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `cover` | `string` | yes | Lossless cover image (PNG/BMP/PGM). |
| `password` | `string` | yes | Message encryption password (>= 8 chars). |
| `private_key_pem` | `string` | yes | Password-encrypted PKCS#8 PEM. |
| `key_password` | `string` | yes | Password that unlocks the private key. |
| `method` | `"lsb_replace" \| "lsb_match" \| "lsb2_replace" \| "suniward" \| "hill"` | no | S-UNIWARD and HILL use STC to encode recoverable messages. |
| `mode` | `"keyed" \| "sequential"` | no |  |
| `message` | `string \| null` | no | Text message. |
| `message_file` | `string \| null` | no | File to hide instead. |
| `stego_passphrase` | `string \| null` | no |  |

Response `200` (`EmbedResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `stego_png_base64` | `string` | yes |  |
| `manifest` | `object` | yes |  |
| `metrics` | `EmbedMetrics` | yes |  |
| `diff_png_base64` | `string` | yes |  |
| `warnings` | `string[]` | yes |  |
| `sender_fingerprint` | `string` | yes |  |

Possible error statuses: `400`, `413`, `415`, `429`

## `POST /api/extract`

**Extract Message**

Run the ordered receiver stages; content is returned only if all pass.

Stage failures (wrong key, tampering, wrong password) are reported inside
a normal 200 response so the UI can show exactly which stage stopped.

Request body (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | `string` | yes | Stego PNG to read. |
| `password` | `string` | yes | Message password. |
| `public_key_pem` | `string` | yes | Sender's public key PEM. |
| `mode` | `"keyed" \| "sequential"` | no |  |
| `technique` | `"auto" \| "lsb" \| "lsb2" \| "stc"` | no | Auto-detects LSB, 2-LSB, or STC framing. |
| `stego_passphrase` | `string \| null` | no |  |

Response `200` (`ExtractResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `stages` | `Stage[]` | yes |  |
| `verified` | `boolean` | yes |  |
| `plaintext` | `string \| null` | no |  |
| `file_base64` | `string \| null` | no |  |
| `filename` | `string \| null` | no |  |
| `supplied_key_fingerprint` | `string` | yes |  |

Possible error statuses: `400`, `413`

## `GET /api/health`

**Health Check**

Report service status, version, and loaded trained models.

Response `200` (`HealthResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `string` | yes |  |
| `version` | `string` | yes |  |
| `models_loaded` | `string[]` | yes |  |

## `POST /api/keys/generate`

**Generate Keys**

Generate a keypair; the private key is returned only password-encrypted.

The server does not store either key. The client must save the encrypted
private key and share the public key (and its fingerprint) out of band.

Request body (`application/json`):

| Field | Type | Required | Description |
|---|---|---|---|
| `key_password` | `string` | yes |  |

Response `200` (`KeyGenerateResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `public_key_pem` | `string` | yes |  |
| `private_key_pem_encrypted` | `string` | yes |  |
| `fingerprint` | `string` | yes |  |
| `fingerprint_short` | `string` | yes |  |

Possible error statuses: `429`

## `GET /api/models`

**List Models**

List registered models and the status of each detector family.

Response `200` (`ModelsResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `models` | `ModelInfo[]` | yes |  |
| `detectors` | `object` | yes |  |
| `load_warnings` | `string[]` | yes |  |
| `ensemble` | `object \| null` | yes |  |

## `GET /api/results`

**Get Results**

Return ``results/metrics.json`` exactly as the evaluation script wrote it.

The UI shows only these numbers. If evaluation has not been run, the
response is MODEL_UNAVAILABLE rather than placeholder values.

Response `200` (`Response Get Results Api Results Get`):

## `GET /api/results/plots`

**List Plots**

List available plot images.

Response `200` (`Response List Plots Api Results Plots Get`):

## `GET /api/results/plots/{name}`

**Get Plot**

Serve one evaluation plot PNG.

## `POST /api/verify`

**Verify Image**

Check (A) pixel hash, (B) manifest signature, (C) embedded packet signature.

Check C runs only when ``mode`` is given (and, for keyed mode, a stego
passphrase), because the packet cannot be located otherwise.

Request body (`multipart/form-data`):

| Field | Type | Required | Description |
|---|---|---|---|
| `image` | `string` | yes | Image to check. |
| `manifest` | `string` | yes | Signed manifest JSON text. |
| `public_key_pem` | `string` | yes | Sender's public key PEM. |
| `mode` | `"keyed" \| "sequential" \| null` | no |  |
| `stego_passphrase` | `string \| null` | no |  |

Response `200` (`VerifyResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `checks` | `VerifyChecks` | yes |  |
| `overall_ok` | `boolean` | yes |  |

Possible error statuses: `400`, `413`

## `GET /health`

**Health Check**

Report service status, version, and loaded trained models.

Response `200` (`HealthResponse`):

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `string` | yes |  |
| `version` | `string` | yes |  |
| `models_loaded` | `string[]` | yes |  |
