import { useMutation } from '@tanstack/react-query';
import { Swords } from 'lucide-react';
import { useEffect, useState } from 'react';

import { api } from '../api/client';
import type { DetectResult, EmbedResult, KeyPair, Method, Mode } from '../api/types';
import { DemoButton, useDemoMode } from '../components/DemoTools';
import { ImageDropzone } from '../components/ImageDropzone';
import { Callout, ErrorBanner, MetricCard, PageHeader, Segmented, Spinner } from '../components/ui';
import { loadDemoCoverInfo } from '../lib/demo';
import { formatNumber, verdictWords } from '../lib/format';
import { readPixels } from '../lib/pixels';
import { DETECTOR_INFO } from './Detect';

// Demo-only credentials, generated in the browser per visit and never reused.
function randomSecret(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return btoa(String.fromCharCode(...bytes));
}

function randomText(length: number): string {
  // Random printable characters do not compress, so payload size is exact.
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const bytes = crypto.getRandomValues(new Uint8Array(length));
  return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join('');
}

/** S-UNIWARD and HILL carry their message through syndrome-trellis codes (STC). */
export function isAdaptive(method: Method): boolean {
  return method === 'suniward' || method === 'hill';
}

/**
 * Message length so the total embedded bits ≈ bpp × pixels (Section 6.2).
 *
 * The STC methods reserve 64 more bits than plain LSB for their own length field, which is
 * included here so the requested payload is not exceeded.
 */
export function messageLengthFor(bpp: number, pixels: number, mode: Mode, method: Method = 'lsb_replace'): number {
  const overheadBits = 104 + (mode === 'keyed' ? 128 : 0) + (isAdaptive(method) ? 64 : 0) + (128 + 1) * 8;
  return Math.max(1, Math.floor((bpp * pixels - overheadBits) / 8));
}

interface RaceOutcome {
  embed: EmbedResult;
  coverScan: DetectResult;
  stegoScan: DetectResult;
}

export function ArmsRace() {
  const [cover, setCover] = useState<File | null>(null);
  const [pixels, setPixels] = useState<number | null>(null);
  const [method, setMethod] = useState<Method>('lsb_replace');
  const [mode, setMode] = useState<Mode>('keyed');
  const [bpp, setBpp] = useState(0.4);
  const [demoKey, setDemoKey] = useState<{ pair: KeyPair; keyPassword: string } | null>(null);
  const demo = useDemoMode();

  useEffect(() => {
    setPixels(null);
    if (cover) void readPixels(cover).then((image) => setPixels(image.width * image.height));
  }, [cover]);

  const race = useMutation({
    mutationFn: async (): Promise<RaceOutcome> => {
      if (!cover || !pixels) throw new Error('Choose a cover image first.');
      let key = demoKey;
      if (!key) {
        const keyPassword = randomSecret();
        key = { pair: await api.generateKeys(keyPassword), keyPassword };
        setDemoKey(key);
      }
      const embed = await api.embed({
        cover,
        message: randomText(messageLengthFor(bpp, pixels, mode, method)),
        password: randomSecret(),
        privateKeyPem: key.pair.private_key_pem_encrypted,
        keyPassword: key.keyPassword,
        method,
        mode,
      });
      const stego = new Blob([Uint8Array.from(atob(embed.stego_png_base64), (c) => c.charCodeAt(0))], { type: 'image/png' });
      const [coverScan, stegoScan] = await Promise.all([
        api.detect({ image: cover, explain: false }),
        api.detect({ image: stego, explain: false }),
      ]);
      return { embed, coverScan, stegoScan };
    },
  });

  return (
    <div>
      <PageHeader title="Compare detectors">
        Hide a random message at a chosen payload and see how each detector scores the clean and the
        modified image. Low payloads and the matching method are the hardest to detect.
      </PageHeader>
      {demo && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <DemoButton onClick={async () => setCover((await loadDemoCoverInfo()).file)}>Load the demo cover</DemoButton>
        </div>
      )}
      <section className="card mb-6 grid gap-5 lg:grid-cols-3">
        <ImageDropzone label="Original image" file={cover} onChange={setCover} losslessOnly />
        <div className="space-y-4 lg:col-span-2">
          <div className="grid gap-4 md:grid-cols-2">
            <Segmented label="Method" value={method} onChange={setMethod} options={[{ value: 'lsb_replace', label: 'LSB replacement' }, { value: 'lsb_match', label: 'LSB matching' }, { value: 'lsb2_replace', label: '2-LSB' }, { value: 'suniward', label: 'S-UNIWARD (STC)', hint: 'Changes favor busy, textured regions' }, { value: 'hill', label: 'HILL (STC)', hint: 'Changes favor busy, textured regions' }]} />
            <Segmented label="Mode" value={mode} onChange={setMode} options={[{ value: 'keyed', label: 'Keyed' }, { value: 'sequential', label: 'Sequential' }]} />
          </div>
          <label className="block">
            <span className="field-label">
              Payload: <span className="mono">{bpp.toFixed(2)} bpp</span>
            </span>
            <input type="range" min={0.01} max={1} step={0.01} value={bpp} onChange={(event) => setBpp(Number(event.target.value))} className="w-full accent-[rgb(var(--accent))]" />
            <span className="hint">
              bpp means bits per pixel: how much is hidden. 0.10 is one hidden bit for every ten pixels; 1.00 uses
              every pixel.
            </span>
          </label>
          <button type="button" className="btn-primary" disabled={!cover || !pixels || race.isPending} onClick={() => race.mutate()}>
            {race.isPending ? <Spinner label="Embedding and scanning…" /> : <><Swords className="h-4 w-4" /> Embed and scan</>}
          </button>
          <p className="hint">Uses a throw-away demo keypair and random message generated in your browser.</p>
          <ErrorBanner error={race.error} />
        </div>
      </section>

      {race.data && (
        <div className="mb-6 grid gap-6 lg:grid-cols-2">
          <section className="card space-y-3">
            <h2 className="section-title">Hiding</h2>
            <div className="grid grid-cols-2 gap-3">
              <MetricCard label="PSNR" value={formatNumber(race.data.embed.metrics.psnr, 1)} unit="dB" />
              <MetricCard label="SSIM" value={formatNumber(race.data.embed.metrics.ssim, 5)} />
              <MetricCard label="Actual payload" value={formatNumber(race.data.embed.metrics.bpp, 3)} unit="bpp" />
              <MetricCard label="Samples changed" value={formatNumber(race.data.embed.metrics.bits_changed_pct, 2)} unit="%" />
            </div>
          </section>
          <section className="card space-y-3">
            <h2 className="section-title">Detection scores</h2>
            <table className="w-full text-sm">
              <caption className="sr-only">Detector scores for the original image and the image with a hidden message</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase text-muted">
                  <th scope="col" className="py-2">Detector</th>
                  <th scope="col" className="text-right">Original</th>
                  <th scope="col" className="text-right">With message</th>
                </tr>
              </thead>
              <tbody>
                {(['statistical', 'rf', 'cnn'] as const).map((name) => {
                  const coverEntry = race.data.coverScan.detectors[name];
                  const stegoEntry = race.data.stegoScan.detectors[name];
                  return (
                    <tr key={name} className="border-b border-line/60">
                      <th scope="row" className="py-2 text-left font-medium">{DETECTOR_INFO[name].title}</th>
                      <td className="mono text-right">{coverEntry?.available ? formatNumber(coverEntry.probability, 3) : 'n/a'}</td>
                      <td className="mono text-right">{stegoEntry?.available ? formatNumber(stegoEntry.probability, 3) : 'n/a'}</td>
                    </tr>
                  );
                })}
                <tr>
                  <th scope="row" className="py-2 text-left font-semibold">Final verdict</th>
                  <td className="text-right text-xs">{verdictWords(race.data.coverScan.label)}</td>
                  <td className="text-right text-xs">{verdictWords(race.data.stegoScan.label)}</td>
                </tr>
              </tbody>
            </table>
            <p className="hint">One image is only an example, not a measure of how accurate a detector is.</p>
          </section>
        </div>
      )}

      <section className="space-y-4">
        <h2 className="section-title">Why some embeddings are harder to detect</h2>
        <div className="grid gap-3 md:grid-cols-2">
          <Callout tone="info" title="Why low payloads are hard">
            At 0.05 bpp only ~5% of samples carry a bit and about half of those already match, so the
            statistics move very little away from natural-image noise.
          </Callout>
          <Callout tone="info" title="Why LSB matching is harder">
            Replacement only ever pairs 2k ↔ 2k+1, which chi-square, RS and SPA exploit. Matching&apos;s ±1
            steps cross those pairs, removing the asymmetry those attacks rely on.
          </Callout>
        </div>
      </section>
    </div>
  );
}
