export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (!Number.isFinite(value)) return value > 0 ? '∞' : '−∞';
  return value.toFixed(digits);
}

/** Shorten a long hex string for compact display, keeping both ends. */
export function shortHash(hash: string, keep = 8): string {
  const clean = hash.replace(/\s+/g, '');
  return clean.length <= keep * 2 ? clean : `${clean.slice(0, keep)}…${clean.slice(-keep)}`;
}

export function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b(\w)/g, (match) => match.toUpperCase());
}

export const METHOD_LABELS: Record<string, string> = {
  lsb_replace: 'LSB replacement',
  lsb_match: 'LSB matching (±1)',
  lsb2_replace: '2-LSB replacement',
  suniward_sim: 'S-UNIWARD (simulated)',
  hill_sim: 'HILL (simulated)',
};

export const MODE_LABELS: Record<string, string> = {
  keyed: 'Keyed scatter',
  sequential: 'Sequential (naive)',
  simulated: 'Simulated',
};

export const STAGE_LABELS: Record<string, string> = {
  read_image: 'Read image',
  extract_bits: 'Extract hidden bits',
  parse_packet: 'Parse packet',
  check_sender: 'Check sender fingerprint',
  verify_signature: 'Verify Ed25519 signature',
  derive_key_and_decrypt: 'Derive key & decrypt (AES-GCM)',
};

/** The one wording used for a detector label on every page. */
export function verdictWords(label: string): string {
  return label === 'suspected_stego' ? 'Hidden data suspected' : 'Not flagged';
}
