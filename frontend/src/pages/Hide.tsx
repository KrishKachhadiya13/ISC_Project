import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, ArrowLeft, ArrowRight, Download, KeyRound, Lock } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import type { EmbedResult, KeyPair, Method, Mode } from '../api/types';
import { BeforeAfter } from '../components/BeforeAfter';
import { ImageDropzone } from '../components/ImageDropzone';
import { ProofPanel } from '../components/ProofPanel';
import { KeyInput } from '../components/KeyInput';
import { SecretInput } from '../components/SecretInput';
import { DemoButton, useDemoMode } from '../components/DemoTools';
import { Stepper } from '../components/Stepper';
import {
  Callout,
  ErrorBanner,
  MetricCard,
  PageHeader,
  Segmented,
  Spinner,
} from '../components/ui';
import { DEMO, loadDemoCover, setDemoArtifacts } from '../lib/demo';
import { base64ToBlob, downloadBlob, downloadText } from '../lib/download';
import { formatBytes, formatNumber } from '../lib/format';
import { MIN_PASSWORD_LENGTH } from '../lib/password';
import { backendChannels, readPixels } from '../lib/pixels';

const STEPS = ['Cover', 'Message', 'Keys & method', 'Result'];
const PACKET_OVERHEAD = 128; // Section 6.4
const HEADER_BITS = 104; // Section 6.2
const SALT_BITS = 128;

/** Largest text message (bytes) that fits, following Section 6.2 exactly. */
export function maxMessageBytes(
  samples: number,
  mode: Mode,
  bitsPerSample = 1,
  usesStc = false,
): number {
  // The 128 salt samples hold one bit each; every other sample holds `bitsPerSample` bits.
  const usableSamples = mode === 'keyed' ? samples - SALT_BITS : samples;
  const codingSamples = usesStc ? usableSamples - 64 : usableSamples * bitsPerSample;
  const maxPacket = Math.floor((codingSamples - HEADER_BITS) / 8);
  return Math.max(0, maxPacket - PACKET_OVERHEAD - 1); // 1 byte: text/file kind
}

interface CoverInfo {
  width: number;
  height: number;
  channels: 1 | 3;
}

export function Hide() {
  const [step, setStep] = useState(0);
  const [cover, setCover] = useState<File | null>(null);
  const [coverInfo, setCoverInfo] = useState<CoverInfo | null>(null);
  const [message, setMessage] = useState('');
  const [messageFile, setMessageFile] = useState<File | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [keyMode, setKeyMode] = useState<'generate' | 'existing'>('generate');
  const [generated, setGenerated] = useState<KeyPair | null>(null);
  const [privateKeyPem, setPrivateKeyPem] = useState('');
  const [keyPassword, setKeyPassword] = useState('');
  const [method, setMethod] = useState<Method>('lsb_replace');
  const [mode, setMode] = useState<Mode>('keyed');
  const [separatePassphrase, setSeparatePassphrase] = useState(false);
  const [stegoPassphrase, setStegoPassphrase] = useState('');
  const demo = useDemoMode();
  const [demoError, setDemoError] = useState<unknown>(null);

  useEffect(() => {
    setCoverInfo(null);
    if (!cover) return;
    readPixels(cover)
      .then(async (image) =>
        setCoverInfo({ width: image.width, height: image.height, channels: await backendChannels(cover, image) }),
      )
      .catch(() => setCoverInfo(null));
  }, [cover]);

  const capacity = useMemo(() => {
    if (!coverInfo) return null;
    const samples = coverInfo.width * coverInfo.height * coverInfo.channels;
    return maxMessageBytes(
      samples,
      mode,
      method === 'lsb2_replace' ? 2 : 1,
      method === 'suniward' || method === 'hill',
    );
  }, [coverInfo, mode, method]);

  const messageBytes = messageFile
    ? messageFile.size + 2 + new TextEncoder().encode(messageFile.name).length
    : new TextEncoder().encode(message).length;

  const generateKeys = useMutation({
    mutationFn: () => api.generateKeys(keyPassword),
    onSuccess: (pair) => {
      setGenerated(pair);
      setPrivateKeyPem(pair.private_key_pem_encrypted);
    },
  });

  const embed = useMutation({
    mutationFn: () => {
      if (!cover) throw new Error('Choose a cover image first.');
      return api.embed({
        cover,
        message,
        messageFile,
        password,
        privateKeyPem,
        keyPassword,
        method,
        mode,
        stegoPassphrase: separatePassphrase ? stegoPassphrase : undefined,
      });
    },
    onSuccess: (result) => {
      // Presenter mode keeps the result in memory so Extract, Tamper Lab and Detect can reuse it.
      if (demo && generated && cover) {
        setDemoArtifacts({
          stego: base64ToBlob(result.stego_png_base64, 'image/png'),
          manifest: result.manifest,
          publicKeyPem: generated.public_key_pem,
          fingerprint: generated.fingerprint,
          method,
          mode,
          coverName: cover.name,
        });
      }
      setStep(3);
    },
  });

  async function fillDemo(text: string = DEMO.message) {
    setDemoError(null);
    try {
      setCover(await loadDemoCover());
      setMessageFile(null);
      setMessage(text);
      setPassword(DEMO.password);
      setConfirm(DEMO.password);
      setKeyMode('generate');
      setKeyPassword(DEMO.keyPassword);
      const pair = await api.generateKeys(DEMO.keyPassword);
      setGenerated(pair);
      setPrivateKeyPem(pair.private_key_pem_encrypted);
      setStep(2);
    } catch (error) {
      setDemoError(error);
    }
  }

  const stepValid = [
    cover !== null,
    (message.length > 0 || messageFile !== null) &&
      password.length >= MIN_PASSWORD_LENGTH &&
      password === confirm &&
      (capacity === null || messageBytes <= capacity),
    privateKeyPem.trim().length > 0 &&
      keyPassword.length >= MIN_PASSWORD_LENGTH &&
      (!separatePassphrase || mode !== 'keyed' || stegoPassphrase.length >= MIN_PASSWORD_LENGTH),
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Hide a message">
        The message is encrypted with a password, signed with a private key, and hidden in the lowest
        bits of a lossless image. Everything is processed in server memory and nothing is stored.
      </PageHeader>
      {demo && step < 3 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <DemoButton onClick={() => void fillDemo()}>Fill demo cover, message and keys</DemoButton>
          <DemoButton onClick={() => void fillDemo(DEMO.longMessage)}>Same, with a longer message</DemoButton>
          <span className="text-xs text-muted">Then press &quot;Hide message&quot; on the last step.</span>
        </div>
      )}
      <ErrorBanner error={demoError} />
      <Stepper steps={STEPS} current={step} />

      <section className="card space-y-5" aria-live="polite">
        {step === 0 && (
          <>
            <ImageDropzone label="Cover image" file={cover} onChange={setCover} losslessOnly />
            {coverInfo && capacity !== null && (
              <div className="grid gap-3 sm:grid-cols-3">
                <MetricCard
                  label="Dimensions"
                  value={`${coverInfo.width}×${coverInfo.height}`}
                  hint={coverInfo.channels === 1 ? 'Grayscale: 1 sample per pixel' : 'RGB: 3 samples per pixel'}
                />
                <MetricCard
                  label="Max message"
                  value={formatBytes(capacity)}
                  hint={`${MODE_HINT[mode]} mode, 1 LSB per sample`}
                />
                <MetricCard
                  label="Payload at max"
                  value={formatNumber(
                    ((capacity + PACKET_OVERHEAD + 1) * 8 + HEADER_BITS) / (coverInfo.width * coverInfo.height),
                    2,
                  )}
                  unit="bpp"
                  hint="Bits per pixel; lower is harder to detect"
                />
              </div>
            )}
          </>
        )}

        {step === 1 && (
          <>
            <div className="flex gap-2" role="group" aria-label="Message type">
              <button
                type="button"
                className={messageFile ? 'btn-secondary' : 'btn-primary'}
                onClick={() => setMessageFile(null)}
              >
                Text
              </button>
              <label className={`${messageFile ? 'btn-primary' : 'btn-secondary'} cursor-pointer`}>
                File…
                <input
                  type="file"
                  className="sr-only"
                  onChange={(event) => {
                    setMessageFile(event.target.files?.[0] ?? null);
                    event.target.value = '';
                  }}
                />
              </label>
            </div>
            {messageFile ? (
              <p className="text-sm">
                Hiding file <span className="font-semibold">{messageFile.name}</span> ({formatBytes(messageFile.size)})
              </p>
            ) : (
              <div>
                <label htmlFor="message" className="field-label">
                  Secret message
                </label>
                <textarea
                  id="message"
                  className="field h-36"
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Type the message to hide…"
                />
              </div>
            )}
            {capacity !== null && (
              <p className={`text-sm ${messageBytes > capacity ? 'text-bad' : 'text-muted'}`}>
                <span className="mono">{formatBytes(messageBytes)}</span> of{' '}
                <span className="mono">{formatBytes(capacity)}</span> capacity
                {messageBytes > capacity && ' — too large for this cover.'}
              </p>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <SecretInput label="Message password" value={password} onChange={setPassword} showStrength />
              <SecretInput
                label="Confirm password"
                value={confirm}
                onChange={setConfirm}
                hint={confirm && confirm !== password ? 'Passwords do not match.' : 'Type it again.'}
              />
            </div>
            <Callout tone="info">
              The key is derived with Argon2id (64 MiB, 3 passes), so weak passwords are slow to guess —
              but a short dictionary word can still be brute-forced. The receiver needs this password.
            </Callout>
          </>
        )}

        {step === 2 && (
          <>
            <Segmented
              label="Signing key"
              value={keyMode}
              onChange={setKeyMode}
              options={[
                { value: 'generate', label: 'Generate a new keypair', hint: 'Download both keys afterwards' },
                { value: 'existing', label: 'Use my existing key', hint: 'Paste your encrypted private key' },
              ]}
            />
            <SecretInput
              label="Private-key password"
              value={keyPassword}
              onChange={setKeyPassword}
              hint="Encrypts (or unlocks) your private key. The server never keeps it."
            />
            {keyMode === 'generate' ? (
              <div className="space-y-3">
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={keyPassword.length < MIN_PASSWORD_LENGTH || generateKeys.isPending}
                  onClick={() => generateKeys.mutate()}
                >
                  {generateKeys.isPending ? <Spinner label="Generating…" /> : <><KeyRound className="h-4 w-4" /> Generate a key pair</>}
                </button>
                <ErrorBanner error={generateKeys.error} />
                {generated && (
                  <div className="space-y-3 rounded-lg border border-line bg-raised p-4">
                    <p className="text-sm">
                      Fingerprint (share with the receiver out of band):
                      <span className="mono mt-1 block break-all text-accent">{generated.fingerprint}</span>
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className="btn-secondary" onClick={() => downloadText(generated.public_key_pem, 'stegaguard_public.pem', 'application/x-pem-file')}>
                        <Download className="h-4 w-4" /> Public key
                      </button>
                      <button type="button" className="btn-secondary" onClick={() => downloadText(generated.private_key_pem_encrypted, 'stegaguard_private_encrypted.pem', 'application/x-pem-file')}>
                        <Lock className="h-4 w-4" /> Encrypted private key
                      </button>
                    </div>
                    <p className="hint">Save the private key now — it cannot be recovered later.</p>
                  </div>
                )}
              </div>
            ) : (
              <KeyInput label="Encrypted private key (PEM)" value={privateKeyPem} onChange={setPrivateKeyPem} kind="private" />
            )}
            <Segmented
              label="Embedding method"
              value={method}
              onChange={setMethod}
              options={[
                { value: 'lsb_replace', label: 'LSB replacement', hint: 'The standard method; easiest to detect at high payloads' },
                { value: 'lsb_match', label: 'LSB matching (±1)', hint: 'Harder for the classical statistical tests to detect' },
                { value: 'lsb2_replace', label: '2-LSB replacement', hint: 'Two bits per sample: double the capacity, larger changes' },
                { value: 'suniward', label: 'S-UNIWARD (STC)', hint: 'Content-adaptive costs with syndrome-trellis coding; changes favor textured regions' },
                { value: 'hill', label: 'HILL (STC)', hint: 'Content-adaptive costs with syndrome-trellis coding; changes favor textured regions' },
              ]}
            />
            <Segmented
              label="Embedding mode"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'keyed', label: 'Keyed scatter', hint: 'Bits are scattered across the image using the key; harder to detect and locate' },
                { value: 'sequential', label: 'Sequential (naive)', hint: 'Bits are written in order from the top rows; easy to spot' },
              ]}
            />
            {mode === 'keyed' && (
              <div className="space-y-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={separatePassphrase}
                    onChange={(event) => setSeparatePassphrase(event.target.checked)}
                  />
                  Use a separate stego passphrase (default: same as message password)
                </label>
                {separatePassphrase && (
                  <SecretInput label="Stego passphrase" value={stegoPassphrase} onChange={setStegoPassphrase} hint="Decides where the bits go. The receiver needs it too." />
                )}
              </div>
            )}
            <ErrorBanner error={embed.error} />
          </>
        )}

        {step === 3 && embed.data && cover && (
          <EmbedResultView
            result={embed.data}
            cover={cover}
            message={messageFile ? null : message}
            password={password}
            publicKeyPem={generated?.public_key_pem ?? null}
            mode={mode}
            method={method}
            stegoPassphrase={separatePassphrase ? stegoPassphrase : undefined}
          />
        )}

        <div className="flex justify-between border-t border-line pt-5">
          <button
            type="button"
            className="btn-ghost"
            disabled={step === 0 || embed.isPending}
            onClick={() => setStep((current) => Math.max(0, current - 1))}
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          {step < 2 && (
            <button type="button" className="btn-primary" disabled={!stepValid[step]} onClick={() => setStep(step + 1)}>
              Next <ArrowRight className="h-4 w-4" />
            </button>
          )}
          {step === 2 && (
            <button type="button" className="btn-primary" disabled={!stepValid[2] || embed.isPending} onClick={() => embed.mutate()}>
              {embed.isPending ? <Spinner label="Encrypting, signing, embedding…" /> : 'Hide message'}
            </button>
          )}
          {step === 3 && (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                embed.reset();
                setStep(0);
              }}
            >
              Start over
            </button>
          )}
        </div>
      </section>
    </div>
  );
}

const MODE_HINT: Record<Mode, string> = { keyed: 'Keyed', sequential: 'Sequential' };

function EmbedResultView({
  result,
  cover,
  message,
  password,
  publicKeyPem,
  mode,
  method,
  stegoPassphrase,
}: {
  result: EmbedResult;
  cover: File;
  message: string | null;
  password: string;
  publicKeyPem: string | null;
  mode: Mode;
  method: Method;
  stegoPassphrase?: string;
}) {
  const stegoBlob = useMemo(() => base64ToBlob(result.stego_png_base64, 'image/png'), [result]);
  const [urls, setUrls] = useState<{ cover: string; stego: string } | null>(null);

  useEffect(() => {
    const next = { cover: URL.createObjectURL(cover), stego: URL.createObjectURL(stegoBlob) };
    setUrls(next);
    return () => {
      URL.revokeObjectURL(next.cover);
      URL.revokeObjectURL(next.stego);
    };
  }, [cover, stegoBlob]);

  const baseName = cover.name.replace(/\.[^.]+$/, '') || 'image';
  const { metrics } = result;

  return (
    <div className="space-y-6">
      <Callout tone="ok" title="Message hidden and signed">
        Sender fingerprint: <span className="mono break-all">{result.sender_fingerprint}</span>
      </Callout>
      {result.warnings.map((warning) => (
        <Callout key={warning} tone="warn">
          {warning}
        </Callout>
      ))}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="PSNR" value={formatNumber(metrics.psnr, 1)} unit="dB" hint="Above ~40 dB is invisible to the eye" />
        <MetricCard label="SSIM" value={formatNumber(metrics.ssim, 5)} hint="1.0 = structurally identical" />
        <MetricCard label="Payload" value={formatNumber(metrics.bpp, 4)} unit="bpp" hint={`${metrics.used_bits.toLocaleString()} of ${metrics.capacity_bits.toLocaleString()} bits`} />
        <MetricCard label="Samples changed" value={formatNumber(metrics.bits_changed_pct, 2)} unit="%" hint="About half of embedded bits already match" />
      </div>
      {urls && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h2 className="mb-2 text-sm font-semibold">Before / after</h2>
            <BeforeAfter beforeUrl={urls.cover} afterUrl={urls.stego} />
          </div>
          <div>
            <h2 className="mb-2 text-sm font-semibold">Difference ×50 (amplified)</h2>
            <img
              src={`data:image/png;base64,${result.diff_png_base64}`}
              alt="Amplified difference between cover and stego"
              className="w-full rounded-lg border border-line [image-rendering:pixelated]"
            />
            <p className="hint">Bright pixels are samples whose LSB changed.</p>
          </div>
        </div>
      )}
      <ProofPanel
        cover={cover}
        stego={stegoBlob}
        manifest={result.manifest}
        message={message}
        password={password}
        publicKeyPem={publicKeyPem}
        mode={mode}
        method={method}
        stegoPassphrase={stegoPassphrase}
      />
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn-primary" onClick={() => downloadBlob(stegoBlob, `${baseName}_stego.png`)}>
          <Download className="h-4 w-4" /> Stego PNG (exact bytes)
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => downloadText(JSON.stringify(result.manifest, null, 2), `${baseName}_manifest.json`, 'application/json')}
        >
          <Download className="h-4 w-4" /> Signed manifest
        </button>
        {publicKeyPem && (
          <button
            type="button"
            className="btn-secondary"
            onClick={() => downloadText(publicKeyPem, 'stegaguard_public.pem', 'application/x-pem-file')}
          >
            <Download className="h-4 w-4" /> Public key (for the receiver)
          </button>
        )}
      </div>
      <Callout tone="warn" title="Keep the manifest separate">
        <AlertTriangle className="sr-only" />
        The manifest proves integrity but reveals that a hidden payload exists. Do not send it with the
        image if covertness matters.
      </Callout>
    </div>
  );
}
