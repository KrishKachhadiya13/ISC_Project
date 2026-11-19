import { useState } from 'react';

import { PageHeader } from '../components/ui';

interface Step {
  id: string;
  title: string;
  body: string;
}

const SENDER: Step[] = [
  { id: 'encrypt', title: 'Encrypt', body: 'A 32-byte key is derived from the password with Argon2id (random 16-byte salt, 64 MiB memory). AES-256-GCM encrypts the message with a random 12-byte nonce; the packet header is authenticated as associated data.' },
  { id: 'sign', title: 'Sign', body: 'Ed25519 signs every byte of the packet. This proves who sent it and lets the receiver reject forgeries before spending any effort on decryption.' },
  { id: 'embed', title: 'Embed', body: 'A 13-byte header (magic, version, length, CRC32) and the packet are written into pixel LSBs. In keyed mode a ChaCha20 keystream decides the order of samples and whitens the bits, so they look random and are spread over the whole image.' },
  { id: 'verify', title: 'Verify', body: 'The receiver extracts the bits, checks the sender fingerprint, and verifies the Ed25519 signature. Any failure stops here: nothing is decrypted.' },
  { id: 'decrypt', title: 'Decrypt', body: 'Only after the signature passes is the key derived and AES-GCM decryption attempted. A wrong password fails the GCM tag check. (In keyed mode the receiver cannot even find the message with a wrong password, so it never gets this far.)' },
];

const DEFENDER: Step[] = [
  { id: 'scan', title: 'Measure', body: 'Classical tests measure the statistical traces that hiding in the lowest bits leaves behind: chi-square (compares pairs of pixel values), RS analysis (counts regular and singular pixel groups) and sample-pair analysis.' },
  { id: 'score', title: 'Score', body: 'A gradient-boosting classifier scores 1,068 measurements taken from the image. The neural network first applies a fixed filter that removes the picture content and keeps the faint noise, then learns to tell clean noise from altered noise.' },
  { id: 'explain', title: 'Explain', body: 'One heat map shows which regions the neural network responded to most; another shows where the image has the most fine-grain noise. Both are hints, not proof.' },
];

const PACKET = [
  ['magic', '4', 'b"SGP1"'],
  ['version', '1', '0x01'],
  ['flags', '1', 'bit0 file, bit1 zlib'],
  ['kdf_id', '1', '1 = Argon2id, 2 = scrypt'],
  ['reserved', '1', '0x00'],
  ['sender_fp', '8', 'SHA-256(public key)[:8]'],
  ['salt', '16', 'random, for the KDF'],
  ['nonce', '12', 'random, for AES-GCM'],
  ['ct_len', '4', 'ciphertext length incl. 16-byte tag'],
  ['ciphertext', 'ct_len', 'AES-256-GCM output'],
  ['signature', '64', 'Ed25519 over all preceding bytes'],
];

function StepDiagram({ title, steps }: { title: string; steps: Step[] }) {
  const [active, setActive] = useState(steps[0].id);
  const current = steps.find((step) => step.id === active) ?? steps[0];
  return (
    <section className="card">
      <h2 className="font-bold">{title}</h2>
      <p className="mb-4 mt-1 text-xs text-muted">Select a step to read about it.</p>
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label={title}>
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center gap-2">
            <button
              type="button"
              role="tab"
              id={`tab-${step.id}`}
              aria-selected={active === step.id}
              aria-controls={`panel-${step.id}`}
              onClick={() => setActive(step.id)}
              className={`rounded-full border px-4 py-1.5 text-sm font-semibold ${active === step.id ? 'border-accent bg-accent text-on-accent' : 'border-line text-muted hover:text-fg'}`}
            >
              {step.title}
            </button>
            {index < steps.length - 1 && <span aria-hidden="true" className="text-muted">→</span>}
          </div>
        ))}
      </div>
      <p id={`panel-${current.id}`} role="tabpanel" aria-labelledby={`tab-${current.id}`} className="mt-4 text-sm leading-relaxed">
        {current.body}
      </p>
    </section>
  );
}

export function HowItWorks() {
  return (
    <div className="space-y-6">
      <PageHeader title="How it works">
        Steganography hides that a message exists; cryptography hides what it says; steganalysis tries to
        detect the hiding. StegaGuard combines all three.
      </PageHeader>
      <StepDiagram title="Sender → receiver" steps={SENDER} />
      <StepDiagram title="Detection" steps={DEFENDER} />
      <section className="card">
        <h2 className="mb-3 font-bold">Crypto packet format (128 bytes overhead)</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Packet fields in order</caption>
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase text-muted">
                <th scope="col" className="py-2">Field</th>
                <th scope="col">Bytes</th>
                <th scope="col">Meaning</th>
              </tr>
            </thead>
            <tbody>
              {PACKET.map(([field, bytes, meaning]) => (
                <tr key={field} className="border-b border-line/60">
                  <td className="mono py-1.5">{field}</td>
                  <td className="mono">{bytes}</td>
                  <td>{meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <h2 className="font-bold">Why sign and encrypt?</h2>
          <p className="mt-2 text-sm text-muted">
            GCM protects confidentiality and integrity for anyone who knows the password — including a
            malicious insider. The Ed25519 signature adds sender authentication and lets the receiver reject
            forged packets cheaply, before running Argon2id.
          </p>
        </div>
        <div className="card">
          <h2 className="font-bold">What is bpp?</h2>
          <p className="mt-2 text-sm text-muted">
            Bits per pixel: embedded bits divided by the number of pixels. 1.0 bpp in a grayscale image
            means every pixel&apos;s LSB carries data; 0.05 bpp means one in twenty. Lower payloads are much
            harder to detect.
          </p>
        </div>
      </section>
    </div>
  );
}
