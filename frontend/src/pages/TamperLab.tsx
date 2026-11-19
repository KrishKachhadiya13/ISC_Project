import { useMutation } from '@tanstack/react-query';
import { Download, FlaskConical } from 'lucide-react';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import type { ExtractResult, VerifyResult } from '../api/types';
import { CHECK_LABELS, CheckRow } from '../components/CheckRow';
import { ImageDropzone } from '../components/ImageDropzone';
import { KeyInput } from '../components/KeyInput';
import { SecretInput } from '../components/SecretInput';
import { DemoButton, useDemoArtifacts, useDemoMode } from '../components/DemoTools';
import { VerificationTimeline } from '../components/VerificationTimeline';
import { Badge, Callout, ErrorBanner, PageHeader, Spinner } from '../components/ui';
import { DEMO } from '../lib/demo';
import { downloadBlob } from '../lib/download';
import { explainFailure } from '../lib/receive';
import { useRevealOnResult } from '../lib/useRevealOnResult';
import { cloneImage, encodePng, fromRgba, readPixels, toImageData, type RawImage } from '../lib/pixels';

type Attack = 'none' | 'flip_one' | 'flip_many' | 'noise' | 'crop' | 'resize' | 'jpeg';

const ATTACKS: { value: Attack; label: string; lossless: boolean; explain: string }[] = [
  { value: 'none', label: 'No attack (control)', lossless: true, explain: 'The image is sent unchanged, so every check should pass. This shows the test itself is fair.' },
  { value: 'flip_one', label: 'Flip 1 pixel LSB', lossless: true, explain: 'Changes one pixel value by one. With plain LSB hiding the pixel check fails but the message usually still reads, because that pixel probably carried no message bit. With S-UNIWARD or HILL every pixel takes part in decoding, so the signature check fails too.' },
  { value: 'flip_many', label: 'Flip N random LSBs', lossless: true, explain: 'Random errors hit the bits that carry the message. The built-in checksum or the sender\u2019s signature catches them.' },
  { value: 'noise', label: 'Add ±1 noise', lossless: true, explain: 'Every pixel is nudged by one level up, down or not at all. Invisible to the eye, but it scrambles the layer where the message lives.' },
  { value: 'crop', label: 'Crop 8 px border', lossless: true, explain: 'The picture gets smaller, so every pixel position shifts and the receiver can no longer find where the message was placed.' },
  { value: 'resize', label: 'Resize to 50%', lossless: false, explain: 'Shrinking the picture recomputes every pixel, which destroys the hidden bits.' },
  { value: 'jpeg', label: 'JPEG re-compress', lossless: false, explain: 'JPEG rewrites the lowest bits of every pixel. This is why hidden messages need a lossless format such as PNG.' },
];

function randomIndex(limit: number): number {
  const buffer = new Uint32Array(1);
  crypto.getRandomValues(buffer);
  return buffer[0] % limit;
}

async function applyAttack(source: RawImage, attack: Attack, count: number, quality: number): Promise<Blob> {
  const image = cloneImage(source);
  const total = image.samples.length;
  if (attack === 'flip_one') {
    image.samples[randomIndex(total)] ^= 1;
  } else if (attack === 'flip_many') {
    for (let index = 0; index < count; index += 1) image.samples[randomIndex(total)] ^= 1;
  } else if (attack === 'noise') {
    for (let index = 0; index < total; index += 1) {
      const step = randomIndex(3) - 1;
      image.samples[index] = Math.min(255, Math.max(0, image.samples[index] + step));
    }
  } else if (attack === 'crop') {
    return encodePng(crop(image, 8));
  }
  if (attack === 'resize' || attack === 'jpeg') {
    // Intentionally lossy: the canvas is the attack here (the only place the app re-encodes).
    const canvas = document.createElement('canvas');
    const scale = attack === 'resize' ? 0.5 : 1;
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Canvas 2D is not available.');
    const full = document.createElement('canvas');
    full.width = image.width;
    full.height = image.height;
    full.getContext('2d')?.putImageData(toImageData(image), 0, 0);
    context.drawImage(full, 0, 0, canvas.width, canvas.height);
    if (attack === 'jpeg') {
      return new Promise((resolve, reject) =>
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('JPEG encoding failed.'))), 'image/jpeg', quality / 100),
      );
    }
    const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
    return encodePng(fromRgba(rgba, canvas.width, canvas.height));
  }
  return encodePng(image);
}

function crop(image: RawImage, border: number): RawImage {
  const width = Math.max(1, image.width - 2 * border);
  const height = Math.max(1, image.height - 2 * border);
  const samples = new Uint8ClampedArray(width * height * image.channels);
  for (let row = 0; row < height; row += 1) {
    const start = ((row + border) * image.width + border) * image.channels;
    samples.set(image.samples.subarray(start, start + width * image.channels), row * width * image.channels);
  }
  return { width, height, channels: image.channels, samples };
}

interface Outcome {
  headline: string;
  text: string;
  badge: string;
  tone: 'ok' | 'warn' | 'bad';
  border: string;
}

/** One plain headline for the attacked image: intact, intact but altered, or lost. */
export function describeOutcome(result: LabOutcome): Outcome {
  const { extract, verify } = result;
  if (extract.verified) {
    if (verify?.checks.pixel_hash?.ok === false) {
      return {
        headline: 'The message survived, but the image was altered',
        text: 'The sender\u2019s signature still checks out, yet the pixel check shows the picture is no longer exactly what was signed.',
        badge: 'Message intact, image altered',
        tone: 'warn',
        border: 'border-warn/60',
      };
    }
    return {
      headline: 'The message is intact',
      text: verify
        ? 'Every check passed.'
        : 'The message still verifies. Load the manifest as well to check for any changed pixel.',
      badge: 'Message intact',
      tone: 'ok',
      border: 'border-ok/60',
    };
  }
  const reason = explainFailure(extract.stages);
  return {
    headline: reason?.title ?? 'The message was lost',
    text: `${reason?.text ?? ''} Nothing was decrypted.`,
    badge: 'Message lost',
    tone: 'bad',
    border: 'border-bad/70',
  };
}

export interface LabOutcome {
  attacked: Blob;
  extract: ExtractResult;
  verify: VerifyResult | null;
}

export function TamperLab() {
  const [image, setImage] = useState<File | null>(null);
  const [pixels, setPixels] = useState<RawImage | null>(null);
  const [publicKey, setPublicKey] = useState('');
  const [password, setPassword] = useState('');
  const [manifest, setManifest] = useState<string | null>(null);
  const [attack, setAttack] = useState<Attack>('flip_one');
  const [count, setCount] = useState(500);
  const [quality, setQuality] = useState(95);
  const demo = useDemoMode();
  const saved = useDemoArtifacts();

  useEffect(() => {
    setPixels(null);
    if (image) void readPixels(image).then(setPixels);
  }, [image]);

  const run = useMutation({
    mutationFn: async (): Promise<LabOutcome> => {
      if (!pixels) throw new Error('Load a stego image first.');
      const attacked = await applyAttack(pixels, attack, count, quality);
      // How the message was hidden is worked out by the server, so any hiding method can be attacked.
      const [extract, verify] = await Promise.all([
        api.extract({ image: attacked, password, publicKeyPem: publicKey, mode: 'auto', technique: 'auto' }),
        manifest
          ? api.verify({ image: attacked, manifest, publicKeyPem: publicKey, mode: 'auto', technique: 'auto', stegoPassphrase: password })
          : Promise.resolve(null),
      ]);
      return { attacked, extract, verify };
    },
  });

  const chosen = ATTACKS.find((item) => item.value === attack) ?? ATTACKS[0];
  const resultRef = useRevealOnResult<HTMLDivElement>(run.data);
  const outcome = run.data ? describeOutcome(run.data) : null;

  return (
    <div>
      <PageHeader title="Tamper test">
        Damage a verified image in your browser, then send it to the receiver and see which checks fail.
        Hidden bits are fragile, and the signatures make every change visible.
      </PageHeader>
      {demo && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <DemoButton
            disabled={!saved}
            onClick={() => {
              if (!saved) return;
              setImage(new File([saved.stego], 'demo_stego.png', { type: 'image/png' }));
              setPublicKey(saved.publicKeyPem);
              setPassword(DEMO.password);
              setManifest(JSON.stringify(saved.manifest));
            }}
          >
            Load the image from the Hide step
          </DemoButton>
          {!saved && <span className="text-xs text-muted">Run the Hide step first (presenter mode).</span>}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card space-y-5">
          <ImageDropzone label="Image with the hidden message (PNG)" file={image} onChange={setImage} losslessOnly />
          <KeyInput label="Sender's public key" value={publicKey} onChange={setPublicKey} kind="public" />
          <SecretInput label="Message password" value={password} onChange={setPassword} autoComplete="off" hint="The password the sender used. It is also what locates the message in the image." />
          <div>
            <span className="field-label">Manifest (optional, adds the check that no pixel changed)</span>
            <label className="btn-secondary cursor-pointer">
              {manifest ? 'Manifest loaded' : 'Load manifest.json'}
              <input type="file" accept=".json" className="sr-only" onChange={async (event) => {
                const file = event.target.files?.[0];
                if (file) setManifest(await file.text());
                event.target.value = '';
              }} />
            </label>
          </div>
          <fieldset>
            <legend className="field-label">Attack</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {ATTACKS.map((item) => (
                <label key={item.value} className={`cursor-pointer rounded-lg border p-2.5 text-sm ${attack === item.value ? 'border-accent bg-accent/10' : 'border-line'}`}>
                  <input type="radio" name="attack" className="sr-only" checked={attack === item.value} onChange={() => setAttack(item.value)} />
                  <span className="font-semibold">{item.label}</span>
                  <span className="block text-xs text-muted">{item.lossless ? 'Keeps the PNG format' : 'Lossy: re-saved in your browser'}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {attack === 'flip_many' && (
            <label className="block text-sm">
              Bits to flip: <span className="mono">{count}</span>
              <input type="range" min={1} max={5000} value={count} onChange={(event) => setCount(Number(event.target.value))} className="w-full accent-[rgb(var(--accent))]" />
            </label>
          )}
          {attack === 'jpeg' && (
            <label className="block text-sm">
              JPEG quality: <span className="mono">{quality}</span>
              <input type="range" min={10} max={100} value={quality} onChange={(event) => setQuality(Number(event.target.value))} className="w-full accent-[rgb(var(--accent))]" />
            </label>
          )}
          <Callout tone="info">{chosen.explain}</Callout>
          <button type="button" className="btn-primary w-full" disabled={!pixels || !publicKey || !password || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? <Spinner label="Attacking and verifying…" /> : <><FlaskConical className="h-4 w-4" /> Apply attack and verify</>}
          </button>
          <ErrorBanner error={run.error} />
        </section>
        <section className="space-y-5" aria-live="polite">
          <div ref={resultRef} tabIndex={-1} className="scroll-mt-24 space-y-5 outline-none">
          {!run.data && <div className="card text-sm text-muted">The receiver&apos;s view of the attacked image appears here.</div>}
          {run.data && outcome && (
            <>
              <div className={`card border-2 ${outcome.border}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-lg font-bold">{outcome.headline}</p>
                  <Badge tone={outcome.tone}>{outcome.badge}</Badge>
                </div>
                <p className="mt-2 text-sm text-muted">
                  <span className="font-semibold text-fg">{chosen.label}.</span> {outcome.text}
                </p>
                <button type="button" className="btn-ghost mt-2 px-0 text-xs" onClick={() => downloadBlob(run.data.attacked, `attacked.${attack === 'jpeg' ? 'jpg' : 'png'}`)}>
                  <Download className="h-3.5 w-3.5" /> Download attacked image
                </button>
              </div>
              <div className="card">
                <h2 className="mb-3 font-semibold">What the receiver checked</h2>
                <VerificationTimeline stages={run.data.extract.stages} showCodes={false} />
              </div>
              {run.data.verify && (
                <div className="card space-y-2">
                  <h2 className="font-semibold">Is the image exactly what the sender made?</h2>
                  <CheckRow label={CHECK_LABELS.pixel_hash} check={run.data.verify.checks.pixel_hash} />
                  <CheckRow label={CHECK_LABELS.manifest_signature} check={run.data.verify.checks.manifest_signature} />
                  <CheckRow label={CHECK_LABELS.payload_signature} check={run.data.verify.checks.payload_signature} />
                </div>
              )}
            </>
          )}
          </div>
        </section>
      </div>
    </div>
  );
}
