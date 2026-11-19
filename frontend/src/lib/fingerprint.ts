/**
 * Compute an Ed25519 public-key fingerprint in the browser, so the receiver
 * can compare it with the sender's out-of-band copy before trusting a result.
 *
 * Fingerprint = SHA-256 of the raw 32-byte key (Section 6.5). In the PEM's
 * SubjectPublicKeyInfo DER, those 32 bytes are the last 32 bytes.
 */
export async function publicKeyFingerprint(pem: string): Promise<string | null> {
  const match = pem.match(/-----BEGIN PUBLIC KEY-----([\s\S]+?)-----END PUBLIC KEY-----/);
  if (!match) return null;
  let der: Uint8Array;
  try {
    const binary = atob(match[1].replace(/\s+/g, ''));
    der = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  } catch {
    return null;
  }
  // Ed25519 SPKI is always 44 bytes: a 12-byte header and the 32-byte key.
  if (der.length !== 44) return null;
  const digest = await crypto.subtle.digest('SHA-256', der.slice(12));
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  return groupHex(hex);
}

export function groupHex(hex: string): string {
  return hex.replace(/\s+/g, '').match(/.{1,4}/g)?.join(' ') ?? hex;
}

export async function sha256Hex(data: Blob | ArrayBuffer): Promise<string> {
  const buffer = data instanceof Blob ? await data.arrayBuffer() : data;
  const digest = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}
