// Types mirror backend/app/api/schemas.py. Keep them in sync.

export type ErrorCode =
  | 'INVALID_IMAGE'
  | 'UNSUPPORTED_FORMAT'
  | 'IMAGE_TOO_LARGE'
  | 'CAPACITY_EXCEEDED'
  | 'WEAK_PASSWORD'
  | 'BAD_KEY'
  | 'KEY_MISMATCH'
  | 'NO_HIDDEN_DATA'
  | 'VERIFICATION_FAILED'
  | 'DECRYPTION_FAILED'
  | 'MODEL_UNAVAILABLE'
  | 'RATE_LIMITED'
  | 'BAD_REQUEST'
  | 'NOT_FOUND'
  | 'INTERNAL'
  | 'NETWORK';

export interface ErrorBody {
  code: ErrorCode;
  message: string;
  details: Record<string, unknown>;
}

export interface Health {
  status: string;
  version: string;
  models_loaded: string[];
}

export interface KeyPair {
  public_key_pem: string;
  private_key_pem_encrypted: string;
  fingerprint: string;
  fingerprint_short: string;
}

export type Method = 'lsb_replace' | 'lsb_match' | 'lsb2_replace' | 'suniward' | 'hill';
/** Which decoder the receiver reads: automatic, 1-bit LSB, 2-LSB, or STC. */
export type Technique = 'auto' | 'lsb' | 'lsb2' | 'stc';
export type Mode = 'keyed' | 'sequential';
/** What the receiver may be told about placement: a specific mode, or find it automatically. */
export type ReceiveMode = Mode | 'auto';
export type OperatingPoint = 'balanced' | 'low_false_alarm';
export type DetectorName = 'statistical' | 'rf' | 'cnn';

export interface Manifest {
  version: number;
  created_at: string;
  cover_pixel_sha256?: string;
  stego_pixel_sha256: string;
  stego_file_sha256: string;
  dimensions: [number, number];
  channels: number;
  method: Method;
  mode: Mode;
  payload_bytes: number;
  payload_bpp: number;
  sender_fingerprint: string;
  signature: string;
  [key: string]: unknown;
}

export interface EmbedMetrics {
  mse: number;
  psnr: number;
  ssim: number;
  bpp: number;
  bits_changed_pct: number;
  capacity_bits: number;
  used_bits: number;
}

export interface EmbedResult {
  stego_png_base64: string;
  manifest: Manifest;
  metrics: EmbedMetrics;
  diff_png_base64: string;
  warnings: string[];
  sender_fingerprint: string;
}

export type StageStatus = 'passed' | 'failed' | 'skipped';

export interface Stage {
  name: string;
  status: StageStatus;
  detail: string;
  code: string | null;
}

export interface ExtractResult {
  stages: Stage[];
  verified: boolean;
  plaintext: string | null;
  file_base64: string | null;
  filename: string | null;
  /** Bit depth the packet was found at; null when extraction failed. */
  technique: 'lsb' | 'lsb2' | 'stc' | null;
  /** Placement mode that worked; null when nothing was recovered. */
  mode: Mode | null;
  supplied_key_fingerprint: string;
}

export interface CheckResult {
  ok: boolean | null;
  detail: string;
}

export interface VerifyResult {
  checks: {
    pixel_hash: CheckResult;
    manifest_signature: CheckResult;
    payload_signature: CheckResult | null;
  };
  overall_ok: boolean;
}

export interface DetectorEntry {
  available: boolean;
  trained: boolean;
  model?: string;
  probability?: number;
  label?: 'clean' | 'suspected_stego';
  threshold?: number;
  reason?: string;
  components?: Record<string, number>;
  [key: string]: unknown;
}

export interface DetectResult {
  label: 'clean' | 'suspected_stego';
  probability: number;
  threshold: number;
  operating_point: OperatingPoint;
  decision_source: string;
  detectors: Partial<Record<DetectorName, DetectorEntry>>;
  features: Record<string, number>;
  heatmap_gradcam_png_base64: string | null;
  heatmap_residual_png_base64: string | null;
  warnings: string[];
  latency_ms: number;
  image_sha256: string;
  width: number;
  height: number;
  channels: number;
}

export interface BatchItem {
  filename: string;
  result: DetectResult | null;
  error: ErrorBody | null;
}

export interface ModelInfo {
  name: string;
  loaded: boolean;
  metadata: Record<string, unknown>;
}

export interface ModelsResult {
  models: ModelInfo[];
  detectors: Record<DetectorName, DetectorEntry>;
  load_warnings: string[];
  ensemble: Record<string, unknown> | null;
}
