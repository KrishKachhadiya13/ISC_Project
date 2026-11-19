import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import type { Manifest, Mode } from '../api/types';
import { shortHash } from '../lib/format';
import { readPixels } from '../lib/pixels';
import { explainChange, findBusiestPatch, firstChangedIndex, largestChange, type PatchProof, type ProofMethod } from '../lib/proof';
import { VerificationTimeline } from './VerificationTimeline';
import { Badge, Callout, ErrorBanner, Spinner } from './ui';

interface Props {
  cover: File;
  /** The exact stego PNG bytes the user can download. */
  stego: Blob;
  manifest: Manifest;
  /** The text that was hidden, or null when a file was hidden. */
  message: string | null;
  password: string;
  /** Needed to check the signature; null when the user supplied their own private key. */
  publicKeyPem: string | null;
  mode: Mode;
  method: ProofMethod;
  stegoPassphrase?: string;
}

type Attempt = { label: string; password: string };

function PatchTable({ title, values, other, highlight }: { title: string; values: number[]; other: number[]; highlight: boolean }) {
  const size = Math.round(Math.sqrt(values.length));
  return (
    <div>
      <p className="mb-2 text-sm font-semibold">{title}</p>
      <div className="overflow-x-auto">
        <table className="mono border-separate border-spacing-0.5 text-xs">
          <caption className="sr-only">{title}: raw pixel values of an {size} by {size} patch</caption>
          <tbody>
            {Array.from({ length: size }, (_, row) => (
              <tr key={row}>
                {Array.from({ length: size }, (_, column) => {
                  const index = row * size + column;
                  const changed = values[index] !== other[index];
                  return (
                    <td
                      key={column}
                      className={`h-7 w-9 rounded text-center ${
                        changed && highlight ? 'bg-accent/25 font-bold text-fg ring-1 ring-accent' : 'bg-raised/60 text-muted'
                      }`}
                      aria-label={changed ? `changed: ${other[index]} became ${values[index]}` : undefined}
                    >
                      {values[index]}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Three pieces of evidence that a message really is in the image, shown on the Hide result:
 * different pixel fingerprints, the raw pixel values where the message left changes, and a
 * live read-back of the message from the exact PNG bytes (plus a wrong-password test).
 */
export function ProofPanel({ cover, stego, manifest, message, password, publicKeyPem, mode, method, stegoPassphrase }: Props) {
  const [patch, setPatch] = useState<PatchProof | null>(null);
  const [patchFailed, setPatchFailed] = useState(false);
  const [attempt, setAttempt] = useState<Attempt | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPatch(null);
    setPatchFailed(false);
    Promise.all([readPixels(cover), readPixels(stego)])
      .then(([before, after]) => {
        if (cancelled) return;
        const found = findBusiestPatch(before, after);
        setPatch(found);
        setPatchFailed(found === null);
      })
      .catch(() => !cancelled && setPatchFailed(true));
    return () => {
      cancelled = true;
    };
  }, [cover, stego]);

  const readBack = useMutation({
    mutationFn: (next: Attempt) => {
      if (!publicKeyPem) throw new Error('No public key is available in this session.');
      return api.extract({
        image: stego,
        password: next.password,
        publicKeyPem,
        mode,
        technique: 'auto',
        stegoPassphrase,
      });
    },
  });

  function run(next: Attempt) {
    setAttempt(next);
    readBack.mutate(next);
  }

  const index = patch ? firstChangedIndex(patch) : -1;
  const before = patch && index >= 0 ? patch.cover[index] : null;
  const after = patch && index >= 0 ? patch.stego[index] : null;
  const result = readBack.data;
  const matches = result?.verified && message !== null ? result.plaintext === message : null;

  return (
    <section className="card space-y-8" aria-labelledby="proof-title">
      <div>
        <h2 id="proof-title" className="section-title">
          Prove the message is hidden
        </h2>
        <p className="mt-2 text-sm text-muted">
          The two pictures look the same, so here is the evidence, in three steps: the image really changed, here
          are the actual pixel values that changed, and the message can be read back out of the image file.
        </p>
      </div>

      <div>
        <h3 className="text-base font-bold">1. The pixels are different</h3>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-line bg-raised/40 p-3">
            <dt className="eyebrow">Original image (pixel fingerprint)</dt>
            <dd className="mono mt-1 break-all text-sm" title={manifest.cover_pixel_sha256}>
              {manifest.cover_pixel_sha256 ? shortHash(manifest.cover_pixel_sha256, 14) : 'not available'}
            </dd>
          </div>
          <div className="rounded-lg border border-accent/40 bg-accent/5 p-3">
            <dt className="eyebrow">Image with the message (pixel fingerprint)</dt>
            <dd className="mono mt-1 break-all text-sm" title={manifest.stego_pixel_sha256}>
              {shortHash(manifest.stego_pixel_sha256, 14)}
            </dd>
          </div>
        </dl>
        <p className="hint">
          A fingerprint (SHA-256) changes completely if even one pixel changes. These two differ, so the image
          was altered, even though no one can see it. The second fingerprint is signed in the manifest.
        </p>
      </div>

      <div>
        <h3 className="text-base font-bold">2. The pixel values that changed</h3>
        {patch ? (
          <>
            <p className="mt-2 text-sm text-muted">
              This is the 8 × 8 patch of the image where the message left the most changes, at position (
              {patch.x}, {patch.y}){patch.channels === 3 ? `, shown for the ${['red', 'green', 'blue'][patch.channel]} channel` : ''}.
              Each number is one pixel&apos;s brightness from 0 to 255. Highlighted cells are the pixels that
              changed.
            </p>
            <div className="mt-4 grid gap-6 md:grid-cols-2">
              <PatchTable title="Original" values={patch.cover} other={patch.stego} highlight={false} />
              <PatchTable title="With the message" values={patch.stego} other={patch.cover} highlight />
            </div>
            <p className="mt-4 text-sm">
              <span className="font-semibold">{patch.changed} of {patch.size * patch.size}</span> pixels in this
              patch changed, by at most <span className="font-semibold">{largestChange(patch)}</span> out of 255. That
              is far too small to see.
            </p>
            {before !== null && after !== null && (
              <p className="mt-2 rounded-lg border border-line bg-raised/40 p-3 text-sm">
                Take one changed pixel: <span className="mono">{before}</span> became <span className="mono">{after}</span>.{' '}
                {explainChange(method, before, after)}
              </p>
            )}
          </>
        ) : patchFailed ? (
          <p className="mt-2 text-sm text-muted">The pixel values could not be compared in this browser.</p>
        ) : (
          <div className="mt-3">
            <Spinner label="Comparing pixels…" />
          </div>
        )}
      </div>

      <div>
        <h3 className="text-base font-bold">3. Read the message back from the image</h3>
        <p className="mt-2 text-sm text-muted">
          This sends the exact image file you can download, together with your password and public key, to the
          receiving side. If the message comes back, it was in the pixels.
        </p>
        {publicKeyPem ? (
          <>
            <div className="mt-4 flex flex-wrap gap-3">
              <button type="button" className="btn-primary" disabled={readBack.isPending} onClick={() => run({ label: 'correct', password })}>
                Read the message back
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={readBack.isPending}
                onClick={() => run({ label: 'wrong', password: `${password}-wrong` })}
              >
                Try a wrong password
              </button>
            </div>
            <div className="mt-4 space-y-4" aria-live="polite">
              {readBack.isPending && <Spinner label="Checking the image…" />}
              <ErrorBanner error={readBack.error} />
              {result && attempt && !readBack.isPending && (
                <>
                  <div className="flex flex-wrap items-center gap-3">
                    <Badge tone={result.verified ? 'ok' : 'bad'}>
                      {result.verified ? 'Message recovered' : 'Nothing recovered'}
                    </Badge>
                    <span className="text-sm text-muted">
                      {attempt.label === 'wrong' ? 'Using a wrong password' : 'Using your password'}
                    </span>
                  </div>
                  <VerificationTimeline stages={result.stages} />
                  {result.verified && result.plaintext !== null && (
                    <div className="rounded-lg border border-ok/40 bg-ok/5 p-4">
                      <p className="eyebrow">Recovered text</p>
                      <p className="mono mt-1 whitespace-pre-wrap break-words text-sm">{result.plaintext}</p>
                      {matches !== null && (
                        <p className="mt-3 text-sm">
                          {matches ? 'This matches the message you typed, character for character.' : 'This does not match the message you typed.'}
                        </p>
                      )}
                      <p className="hint">Read from the pixels of the exact PNG you can download, not from this page.</p>
                    </div>
                  )}
                  {!result.verified && attempt.label === 'wrong' && (
                    <Callout tone="info" title="Why nothing came back">
                      With a wrong password the receiver cannot even find where the message is hidden, and
                      the image looks like any ordinary picture. No partial message is ever returned.
                    </Callout>
                  )}
                </>
              )}
            </div>
          </>
        ) : (
          <Callout tone="info">
            To check from here, generate a key pair in the previous step. Otherwise, open
            &ldquo;Extract &amp; verify&rdquo; and enter the receiver&apos;s public key.
          </Callout>
        )}
      </div>
    </section>
  );
}
