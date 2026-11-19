import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../api/client';
import type { DetectResult, DetectorEntry, OperatingPoint } from '../api/types';
import { BitPlaneViewer } from '../components/BitPlaneViewer';
import { ConfidenceGauge } from '../components/ConfidenceGauge';
import { DemoButton, useDemoArtifacts, useDemoMode } from '../components/DemoTools';
import { HeatmapOverlay } from '../components/HeatmapOverlay';
import { ImageDropzone } from '../components/ImageDropzone';
import { Badge, Callout, ErrorBanner, PageHeader, Segmented, Spinner } from '../components/ui';
import { loadDemoCoverInfo } from '../lib/demo';
import { formatNumber, shortHash } from '../lib/format';
import { useRevealOnResult } from '../lib/useRevealOnResult';

export const DETECTOR_INFO: Record<string, { title: string; text: string; technical: string }> = {
  statistical: {
    title: 'Statistical tests',
    text: 'Classic checks for the pattern that simple hiding leaves in pixel values.',
    technical:
      'A rule-based average of three classical tests (chi-square, RS and sample-pair analysis). It is not trained.',
  },
  rf: {
    title: 'Feature-based classifier',
    text: 'A trained model that studies more than a thousand measurements of the image.',
    technical:
      'A gradient-boosting model trained on 1,068 measurements taken from the image: the classical tests, bit statistics and pixel-difference counts.',
  },
  cnn: {
    title: 'Neural network',
    text: 'A small neural network that looks at the faint noise hiding leaves behind.',
    technical:
      'A small convolutional neural network. A fixed filter first removes the picture content so the network can focus on the faint changes that hiding leaves behind.',
  },
};

export const FEATURE_INFO: Record<string, string> = {
  chi_square_statistic:
    'Chi-square (Westfeld & Pfitzmann 1999): compares histogram pairs (2k, 2k+1). LSB replacement equalises the pairs, so the statistic drops.',
  chi_square_degrees_of_freedom: 'Number of histogram pairs used in the chi-square test.',
  chi_square_p_value:
    'Probability the pair counts look this equal by chance. Near 1 suggests LSB replacement; near 0 suggests a clean image.',
  pair_difference: 'Average |h(2k) − h(2k+1)| / N. Embedding shrinks it.',
  rs_estimate:
    'RS analysis (Fridrich, Goljan & Du 2001): estimated fraction of samples carrying a message, from regular/singular group counts.',
  spa_estimate: 'Sample Pair Analysis (Dumitrescu, Wu & Wang 2003): estimated embedding rate from pixel-pair statistics.',
  rs_r_m: 'Regular groups under the flipping mask M.',
  rs_s_m: 'Singular groups under the flipping mask M.',
  rs_r_neg_m: 'Regular groups under the negative mask −M.',
  rs_s_neg_m: 'Singular groups under −M. In clean images R(−M) ≈ R(M); embedding pulls them apart.',
};

function DetectorCard({ name, entry }: { name: string; entry: DetectorEntry }) {
  const info = DETECTOR_INFO[name] ?? { title: name, text: '', technical: '' };
  const flagged = entry.label === 'suspected_stego';
  return (
    <div className="rounded-lg border border-line bg-raised p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">{info.title}</p>
        {!entry.available ? (
          <Badge tone="neutral">{entry.trained ? 'Skipped' : 'Not trained'}</Badge>
        ) : flagged ? (
          <Badge tone="bad">Suspected</Badge>
        ) : (
          <Badge tone="ok">Not flagged</Badge>
        )}
      </div>
      {entry.available && entry.probability !== undefined ? (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-line" aria-hidden="true">
          <div className={`h-full ${flagged ? 'bg-bad' : 'bg-ok'}`} style={{ width: `${entry.probability * 100}%` }} />
        </div>
      ) : (
        <p className="mt-2 text-sm text-muted">{entry.reason}</p>
      )}
      <p className="mt-2 text-xs text-muted">{info.text}</p>
    </div>
  );
}

export function DetectResultView({ result, imageUrl }: { result: DetectResult; imageUrl: string }) {
  const stego = result.label === 'suspected_stego';
  const demo = useDemoMode();
  const entries = Object.entries(result.detectors).filter((pair): pair is [string, DetectorEntry] => Boolean(pair[1]));
  return (
    <div className="space-y-6">
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="card space-y-4">
          <Badge tone={stego ? 'bad' : 'ok'}>{stego ? 'Hidden data suspected' : 'Not flagged'}</Badge>
          <ConfidenceGauge value={result.probability} threshold={result.threshold} label="Likelihood score" />
          <p className="text-sm text-muted">
            {stego
              ? 'The detectors see patterns typical of hidden data. That is a reason to look closer, not proof.'
              : 'Nothing unusual was found. This does not prove the image is clean: a short message changes too few pixels to notice.'}
          </p>
          {stego && (
            <Link to={{ pathname: '/extract', search: demo ? '?demo=1' : '' }} className="btn-secondary w-full">
              Try to read it in Extract &amp; verify
            </Link>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-1 lg:grid-cols-2">
          {entries.map(([name, entry]) => (
            <DetectorCard key={name} name={name} entry={entry} />
          ))}
        </div>
      </div>
      {result.warnings.map((warning) => (
        <Callout key={warning} tone="warn">
          {warning}
        </Callout>
      ))}
      <div className="card">
        <h2 className="mb-3 font-semibold">Where the detector looked</h2>
        {result.heatmap_gradcam_png_base64 || result.heatmap_residual_png_base64 ? (
          <HeatmapOverlay
            imageUrl={imageUrl}
            gradcamBase64={result.heatmap_gradcam_png_base64}
            residualBase64={result.heatmap_residual_png_base64}
          />
        ) : (
          <p className="text-sm text-muted">
            The heat maps need the trained neural network and an image of at least 256 × 256 pixels.
          </p>
        )}
      </div>
      <details className="card">
        <summary className="cursor-pointer font-semibold">Technical details</summary>
        <div className="mt-4 space-y-6">
          <p className="text-sm text-muted">
            Verdict from: {result.decision_source} · sensitivity: {result.operating_point.replace(/_/g, ' ')} ·{' '}
            {formatNumber(result.latency_ms, 0)} ms · flagged at or above {(result.threshold * 100).toFixed(1)}%.
          </p>
          <ul className="space-y-3">
            {entries.map(([name, entry]) => (
              <li key={name} className="text-sm">
                <p className="font-semibold">{DETECTOR_INFO[name]?.title ?? name}</p>
                {entry.available && entry.probability !== undefined ? (
                  <p className="mono text-xs">
                    Score {formatNumber(entry.probability, 3)} · threshold {formatNumber(entry.threshold, 3)}
                    {entry.model ? ` · ${entry.model}` : ''}
                  </p>
                ) : null}
                <p className="text-xs text-muted">{DETECTOR_INFO[name]?.technical}</p>
              </li>
            ))}
          </ul>
          {Object.keys(result.features).length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Image measurements used by the detectors</caption>
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase text-muted">
                    <th scope="col" className="py-2 pr-3">Measurement</th>
                    <th scope="col" className="py-2 text-right">Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.features).map(([name, value]) => (
                    <tr key={name} className="border-b border-line/60 align-top">
                      <th scope="row" className="py-2 pr-3 text-left font-medium">
                        <span className="mono">{name}</span>
                        {FEATURE_INFO[name] && <span className="mt-0.5 block text-xs font-normal text-muted">{FEATURE_INFO[name]}</span>}
                      </th>
                      <td className="mono py-2 text-right">{formatNumber(value, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mono break-all text-xs text-muted">
            {result.width}×{result.height}×{result.channels} · SHA-256 {shortHash(result.image_sha256, 12)}
          </p>
        </div>
      </details>
    </div>
  );
}

export function Detect() {
  const [image, setImage] = useState<File | null>(null);
  const [operatingPoint, setOperatingPoint] = useState<OperatingPoint>('balanced');
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const demo = useDemoMode();
  const saved = useDemoArtifacts();
  const [fallbackCover, setFallbackCover] = useState(false);

  useEffect(() => {
    if (!image) {
      setImageUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(image);
    setImageUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [image]);

  const scan = useMutation({
    mutationFn: () => {
      if (!image) throw new Error('Choose an image first.');
      return api.detect({ image, operatingPoint });
    },
  });
  const resultRef = useRevealOnResult<HTMLDivElement>(scan.data);

  return (
    <div>
      <PageHeader title="Detect hidden data">
        Upload an image to check whether something may be hidden in it. A high score is a reason to look
        closer; it is not proof.
      </PageHeader>
      {demo && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <DemoButton
            onClick={async () => {
              const cover = await loadDemoCoverInfo();
              setFallbackCover(!cover.inDistribution);
              setImage(cover.file);
            }}
          >
            Load the demo cover
          </DemoButton>
          <DemoButton
            disabled={!saved}
            onClick={() => {
              if (saved) setImage(new File([saved.stego], 'demo_stego.png', { type: 'image/png' }));
            }}
          >
            Load the stego image from Hide
          </DemoButton>
        </div>
      )}
      {demo && fallbackCover && (
        <div className="mb-4">
          <Callout tone="warn" title="Fallback demo cover in use">
            This small JPEG-origin photo differs from the BOSSbase images the detectors were trained on, so
            even a clean copy can be flagged. Run <code className="mono">python -m scripts.make_demo_assets</code>{' '}
            in <code className="mono">backend/</code> to use an in-distribution cover.
          </Callout>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <section className="card h-fit space-y-5" aria-label="Scan settings">
          <ImageDropzone label="Image to scan" file={image} onChange={setImage} description="Lossless formats (PNG, BMP) give meaningful results" />
          <Segmented
            label="Sensitivity"
            value={operatingPoint}
            onChange={setOperatingPoint}
            options={[
              { value: 'balanced', label: 'Balanced', hint: 'Best overall accuracy' },
              { value: 'low_false_alarm', label: 'Fewer false alarms', hint: 'Flags only when quite sure' },
            ]}
          />
          <button type="button" className="btn-primary w-full" disabled={!image || scan.isPending} onClick={() => scan.mutate()}>
            {scan.isPending ? <Spinner label="Scanning…" /> : 'Scan image'}
          </button>
          <ErrorBanner error={scan.error} />
        </section>
        <section aria-live="polite" className="min-w-0 space-y-6">
          <div ref={resultRef} tabIndex={-1} className="scroll-mt-24 outline-none">
            {scan.data && imageUrl ? (
              <DetectResultView result={scan.data} imageUrl={imageUrl} />
            ) : (
              <div className="card text-sm text-muted">Choose an image and press Scan image.</div>
            )}
          </div>
          {image && (
            <details className="card">
              <summary className="cursor-pointer font-semibold">Look at the lowest bit layer</summary>
              <p className="mb-3 mt-3 text-sm text-muted">
                Hiding with simple methods rewrites the lowest bit of the pixels. In a normal photo that layer
                still shows faint shapes; where a message was written it turns to random noise.
              </p>
              <BitPlaneViewer file={image} />
            </details>
          )}
        </section>
      </div>
    </div>
  );
}
