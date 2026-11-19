import type {
  BatchItem,
  DetectResult,
  DetectorName,
  EmbedResult,
  ErrorBody,
  ErrorCode,
  ExtractResult,
  Health,
  KeyPair,
  Method,
  Mode,
  ReceiveMode,
  ModelsResult,
  Technique,
  OperatingPoint,
  VerifyResult,
} from './types';

// Empty base means same origin: the Vite dev proxy (and nginx in Docker)
// forward /api to the backend.
const BASE_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

/** An API failure carrying the backend's stable error code. */
export class ApiError extends Error {
  readonly code: ErrorCode;
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(body: ErrorBody, status: number) {
    super(body.message);
    this.name = 'ApiError';
    this.code = body.code;
    this.details = body.details;
    this.status = status;
  }
}

function isErrorEnvelope(value: unknown): value is { error: ErrorBody } {
  return (
    typeof value === 'object' &&
    value !== null &&
    'error' in value &&
    typeof (value as { error: unknown }).error === 'object'
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      { code: 'NETWORK', message: 'Cannot reach the StegaGuard backend.', details: {} },
      0,
    );
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    if (isErrorEnvelope(body)) throw new ApiError(body.error, response.status);
    throw new ApiError(
      { code: 'INTERNAL', message: `Request failed (HTTP ${response.status}).`, details: {} },
      response.status,
    );
  }
  return body as T;
}

function form(fields: Record<string, string | Blob | undefined | null>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value === undefined || value === null || value === '') continue;
    data.append(key, value);
  }
  return data;
}

export interface EmbedInput {
  cover: File;
  message?: string;
  messageFile?: File | null;
  password: string;
  privateKeyPem: string;
  keyPassword: string;
  method: Method;
  mode: Mode;
  stegoPassphrase?: string;
}

export interface ExtractInput {
  image: Blob;
  password: string;
  publicKeyPem: string;
  mode: ReceiveMode;
  technique?: Technique;
  stegoPassphrase?: string;
}

export interface VerifyInput {
  image: Blob;
  manifest: string;
  publicKeyPem: string;
  mode?: ReceiveMode;
  technique?: Technique;
  stegoPassphrase?: string;
}

export interface DetectInput {
  image: Blob;
  detectors?: DetectorName[] | 'all';
  operatingPoint?: OperatingPoint;
  explain?: boolean;
}

function detectorField(detectors: DetectorName[] | 'all' | undefined): string {
  return !detectors || detectors === 'all' ? 'all' : detectors.join(',');
}

export const api = {
  health: () => request<Health>('/api/health'),

  generateKeys: (keyPassword: string) =>
    request<KeyPair>('/api/keys/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_password: keyPassword }),
    }),

  embed: (input: EmbedInput) =>
    request<EmbedResult>('/api/embed', {
      method: 'POST',
      body: form({
        cover: input.cover,
        message: input.messageFile ? undefined : input.message,
        message_file: input.messageFile ?? undefined,
        password: input.password,
        private_key_pem: input.privateKeyPem,
        key_password: input.keyPassword,
        method: input.method,
        mode: input.mode,
        stego_passphrase: input.stegoPassphrase,
      }),
    }),

  extract: (input: ExtractInput) =>
    request<ExtractResult>('/api/extract', {
      method: 'POST',
      body: form({
        image: input.image,
        password: input.password,
        public_key_pem: input.publicKeyPem,
        mode: input.mode,
        technique: input.technique ?? 'auto',
        stego_passphrase: input.stegoPassphrase,
      }),
    }),

  verify: (input: VerifyInput) =>
    request<VerifyResult>('/api/verify', {
      method: 'POST',
      body: form({
        image: input.image,
        manifest: input.manifest,
        public_key_pem: input.publicKeyPem,
        mode: input.mode,
        technique: input.technique ?? 'auto',
        stego_passphrase: input.stegoPassphrase,
      }),
    }),

  detect: (input: DetectInput) =>
    request<DetectResult>('/api/detect', {
      method: 'POST',
      body: form({
        image: input.image,
        detectors: detectorField(input.detectors),
        operating_point: input.operatingPoint ?? 'balanced',
        explain: String(input.explain ?? true),
      }),
    }),

  detectBatch: (images: File[], operatingPoint: OperatingPoint = 'balanced') => {
    const data = new FormData();
    for (const image of images) data.append('images', image);
    data.append('operating_point', operatingPoint);
    return request<{ items: BatchItem[] }>('/api/detect/batch', { method: 'POST', body: data });
  },

  models: () => request<ModelsResult>('/api/models'),
};
