import { useMutation } from '@tanstack/react-query';
import { Copy, Download, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { api } from '../api/client';
import type { ExtractResult, ReceiveMode, Technique, VerifyResult } from '../api/types';
import { CHECK_LABELS, CheckRow } from '../components/CheckRow';
import { ImageDropzone } from '../components/ImageDropzone';
import { KeyInput } from '../components/KeyInput';
import { SecretInput } from '../components/SecretInput';
import { DemoButton, useDemoArtifacts, useDemoMode } from '../components/DemoTools';
import { VerificationTimeline } from '../components/VerificationTimeline';
import { Badge, Callout, ErrorBanner, PageHeader, Spinner } from '../components/ui';
import { DEMO } from '../lib/demo';
import { base64ToBlob, downloadBlob, downloadText } from '../lib/download';
import { explainFailure } from '../lib/receive';
import { useRevealOnResult } from '../lib/useRevealOnResult';

// The receiver never asks how the message was hidden: the server works it out from the image.
const MODE: ReceiveMode = 'auto';
const TECHNIQUE: Technique = 'auto';

interface Outcome {
  extract: ExtractResult;
  verify: VerifyResult | null;
}

export function ExtractVerify() {
  const [image, setImage] = useState<File | null>(null);
  const [publicKey, setPublicKey] = useState('');
  const [password, setPassword] = useState('');
  const [stegoPassphrase, setStegoPassphrase] = useState('');
  const [manifestText, setManifestText] = useState<string | null>(null);
  const [manifestName, setManifestName] = useState('');
  const demo = useDemoMode();
  const saved = useDemoArtifacts();

  const run = useMutation({
    mutationFn: async (): Promise<Outcome> => {
      if (!image) throw new Error('Choose the image first.');
      const passphrase = stegoPassphrase || undefined;
      const [extract, verify] = await Promise.all([
        api.extract({ image, password, publicKeyPem: publicKey, mode: MODE, technique: TECHNIQUE, stegoPassphrase: passphrase }),
        manifestText
          ? api.verify({
              image,
              manifest: manifestText,
              publicKeyPem: publicKey,
              mode: MODE,
              technique: TECHNIQUE,
              stegoPassphrase: passphrase ?? password,
            })
          : Promise.resolve(null),
      ]);
      return { extract, verify };
    },
  });

  const ready = image !== null && publicKey.trim() !== '' && password.length > 0;
  const resultRef = useRevealOnResult<HTMLDivElement>(run.data);
  const isJpeg = image !== null && (image.type === 'image/jpeg' || /\.jpe?g$/i.test(image.name));

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Extract and verify a message">
        Check that a message really came from the sender and that the image was not altered, then read
        it. The signature is checked <strong>before</strong> anything is decrypted; if a check fails, no
        message is shown.
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
              setStegoPassphrase('');
              setManifestText(JSON.stringify(saved.manifest));
              setManifestName('demo_manifest.json');
            }}
          >
            Load the image from the Hide step
          </DemoButton>
          {!saved && <span className="text-xs text-muted">Run the Hide step first (presenter mode).</span>}
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card space-y-5" aria-label="Inputs">
          <ImageDropzone label="Image with the hidden message" file={image} onChange={setImage} losslessOnly={false} description="The PNG you received" />
          {isJpeg && (
            <Callout tone="warn" title="This looks like a JPEG">
              Saving or sending a picture as JPEG destroys a hidden message. Use the original PNG file.
            </Callout>
          )}
          <KeyInput label="Sender's public key" value={publicKey} onChange={setPublicKey} kind="public" />
          <SecretInput label="Message password" value={password} onChange={setPassword} autoComplete="current-password" hint="The password the sender used." />
          <details className="rounded-lg border border-line px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold">Advanced</summary>
            <div className="mt-3">
              <SecretInput
                label="Separate passphrase (optional)"
                value={stegoPassphrase}
                onChange={setStegoPassphrase}
                autoComplete="off"
                hint="Only if the sender used a different passphrase for placing the message. Leave empty otherwise."
              />
            </div>
          </details>
          <div>
            <span className="field-label">Signed manifest (optional)</span>
            <label className="btn-secondary cursor-pointer">
              {manifestName || 'Load manifest.json'}
              <input
                type="file"
                accept=".json,application/json"
                className="sr-only"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (file) {
                    setManifestText(await file.text());
                    setManifestName(file.name);
                  }
                  event.target.value = '';
                }}
              />
            </label>
            <p className="hint">Adds a check that the image is exactly what the sender made.</p>
          </div>
          <button type="button" className="btn-primary w-full" disabled={!ready || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? <Spinner label="Verifying…" /> : 'Extract and verify'}
          </button>
          <ErrorBanner error={run.error} />
        </section>

        <section className="space-y-5" aria-label="Results" aria-live="polite">
          <div ref={resultRef} tabIndex={-1} className="scroll-mt-24 space-y-5 outline-none">
            {!run.data && !run.isPending && (
              <div className="card text-sm text-muted">The result appears here: what was checked, and the message if everything passes.</div>
            )}
            {run.data && <OutcomeView outcome={run.data} />}
          </div>
        </section>
      </div>
    </div>
  );
}

function OutcomeView({ outcome }: { outcome: Outcome }) {
  const { extract, verify } = outcome;
  const [copy, setCopy] = useState<'idle' | 'copied' | 'failed'>('idle');
  const demo = useDemoMode();
  const reason = extract.verified ? null : explainFailure(extract.stages);
  return (
    <>
      <div className={`card border-2 ${extract.verified ? 'border-ok/60' : 'border-bad/70'}`}>
        <div className="flex items-center gap-3">
          {extract.verified ? (
            <ShieldCheck className="h-8 w-8 shrink-0 text-ok" aria-hidden="true" />
          ) : (
            <ShieldAlert className="h-8 w-8 shrink-0 text-bad" aria-hidden="true" />
          )}
          <div>
            <p className="text-lg font-bold">
              {extract.verified ? 'Message verified' : (reason?.title ?? 'Nothing was decrypted')}
            </p>
            <p className="text-sm text-muted">
              {extract.verified
                ? 'The sender\u2019s signature is valid, so the message is genuine and was read from the image.'
                : `${reason?.text ?? ''} Nothing was decrypted.`}
            </p>
          </div>
        </div>
        <details className="mt-3 text-xs text-muted">
          <summary className="cursor-pointer">Details</summary>
          <p className="mt-2">
            Sender key fingerprint: <span className="mono break-all">{extract.supplied_key_fingerprint}</span>
          </p>
          {extract.technique && (
            <p className="mt-1">
              Found using {extract.mode ? (extract.mode === 'sequential' ? 'in-order placement' : 'key-based placement') : 'automatic placement'}
              {', '}
              {extract.technique === 'lsb2' ? '2-LSB' : extract.technique === 'stc' ? 'adaptive STC' : '1-bit LSB'}.
            </p>
          )}
        </details>
      </div>
      <div className="card">
        <h2 className="mb-3 font-semibold">What the receiver checked</h2>
        <VerificationTimeline stages={extract.stages} showCodes={false} />
      </div>
      {extract.verified && extract.plaintext !== null && (
        <div className="card space-y-3">
          <h2 className="font-semibold">
            Message <span className="text-sm font-normal text-muted">({extract.plaintext.length} characters)</span>
          </h2>
          <pre className="mono max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-bg p-3 text-sm">
            {extract.plaintext}
          </pre>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(extract.plaintext ?? '');
                  setCopy('copied');
                } catch {
                  // Clipboard access is blocked on non-secure pages or when permission is denied.
                  setCopy('failed');
                }
              }}
            >
              <Copy className="h-4 w-4" /> {copy === 'copied' ? 'Copied' : copy === 'failed' ? 'Copy blocked: select the text' : 'Copy'}
            </button>
            <button type="button" className="btn-secondary" onClick={() => downloadText(extract.plaintext ?? '', 'message.txt')}>
              <Download className="h-4 w-4" /> Download
            </button>
          </div>
        </div>
      )}
      {extract.verified && extract.file_base64 && (
        <div className="card">
          <h2 className="mb-3 font-semibold">Hidden file</h2>
          <button
            type="button"
            className="btn-primary"
            onClick={() => downloadBlob(base64ToBlob(extract.file_base64 ?? '', 'application/octet-stream'), extract.filename ?? 'file')}
          >
            <Download className="h-4 w-4" /> {extract.filename}
          </button>
        </div>
      )}
      {verify && (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Is the image exactly what the sender made?</h2>
            <Badge tone={verify.overall_ok ? 'ok' : 'bad'}>{verify.overall_ok ? 'All passed' : 'Failed'}</Badge>
          </div>
          <CheckRow label={CHECK_LABELS.pixel_hash} check={verify.checks.pixel_hash} />
          <CheckRow label={CHECK_LABELS.manifest_signature} check={verify.checks.manifest_signature} />
          <CheckRow label={CHECK_LABELS.payload_signature} check={verify.checks.payload_signature} />
          <Callout tone="info">
            The first check fails if even one pixel changed, even when the message can still be read.
          </Callout>
        </div>
      )}
      <div className="card flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-muted">Want to know whether an image like this can be spotted?</span>
        <Link to={{ pathname: '/detect', search: demo ? '?demo=1' : '' }} className="btn-secondary">
          Scan an image for hidden data
        </Link>
      </div>
    </>
  );
}
