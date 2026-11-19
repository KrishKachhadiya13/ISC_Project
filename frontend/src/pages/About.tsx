import { useModels } from '../api/hooks';
import { Callout, PageHeader } from '../components/ui';
import { DETECTOR_NAMES } from '../lib/project';

const COVERED = [
  ['Adaptive messages', 'S-UNIWARD and HILL use syndrome-trellis coding to carry recoverable messages. Their current detector results still come from the separate simulators.'],
  ['Hiding methods', 'Least-significant-bit replacement, least-significant-bit matching (±1) and 2-bit replacement, each with scattered (keyed) or in-order placement.'],
  ['Cryptography', 'Argon2id key derivation, AES-256-GCM authenticated encryption, SHA-256 hashing, and Ed25519 digital signatures with a signed integrity manifest.'],
  ['Detection', 'Chi-square, RS and sample-pair tests, a feature-based classifier, a convolutional neural network, and a combined verdict.'],
  ['Testing detectors on other techniques', 'Two content-adaptive schemes (S-UNIWARD and HILL) are simulated so the detectors can be tested on methods they were not trained on. These simulations do not carry a message.'],
];

const NOT_COVERED = [
  'Hiding in compressed (JPEG) images, or in audio and video.',
  'Protection against an attacker who controls the server, the device or the browser.',
];

export function About() {
  const models = useModels();
  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <PageHeader title="About">
        How StegaGuard works, what it covers, and where it stops being reliable.
      </PageHeader>

      <section className="space-y-3" aria-labelledby="scope">
        <h2 id="scope" className="section-title">
          Scope
        </h2>
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">What is covered</caption>
          <tbody>
            {COVERED.map(([topic, text]) => (
              <tr key={topic} className="border-b border-line align-top">
                <th scope="row" className="w-48 py-3 pr-4 text-left font-semibold">{topic}</th>
                <td className="py-3 text-muted">{text}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h3 className="font-display text-base font-semibold">Not covered</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          {NOT_COVERED.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="space-y-3" aria-labelledby="limits">
        <h2 id="limits" className="section-title">
          Limitations
        </h2>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted">
          <li>Hidden bits do not survive JPEG compression, resizing, cropping or most social-media uploads.</li>
          <li>The detectors were trained on grayscale images from one public dataset. Colour images and other cameras are scored less reliably.</li>
          <li>Detection is statistical. It produces false alarms and misses, so a high score is a reason to look closer, never proof.</li>
          <li>Python cannot guarantee that secrets are erased from memory after use.</li>
          <li>
            A wrong password and a missing message look the same on purpose. Other failures name the step that
            stopped so each stage can be studied; a real system would reveal less.
          </li>
          <li>Heat maps are hints about where a model responded, not proof that data is hidden.</li>
        </ul>
      </section>

      <Callout tone="warn" title="Acceptable use">
        Use only images and messages that you own or have permission to use. Do not use this site to
        hide content you are not allowed to send, and never treat a detector score as evidence
        against a person: scores are estimates with known error rates.
      </Callout>

      <section className="space-y-2" aria-labelledby="privacy">
        <h2 id="privacy" className="section-title">
          Privacy
        </h2>
        <p className="text-sm text-muted">
          The server keeps nothing. Uploads, messages, passwords and keys are processed in memory and
          are never written to disk or to logs. Private keys are returned only in password-encrypted
          form. The server does see your password and message while it works, so for anything
          sensitive, run it on your own computer.
        </p>
      </section>

      <section className="space-y-2" aria-labelledby="models">
        <h2 id="models" className="section-title">
          Models on this server
        </h2>
        {models.data?.models.length ? (
          <ul className="space-y-1 text-sm text-muted">
            {models.data.models.map((model) => (
              <li key={model.name}>
                {DETECTOR_NAMES[model.name.replace('classical_hgb', 'classical').replace('classical_rf', 'classical')] ?? model.name}{' '}
                <span className="mono text-xs">({model.name})</span>: {model.loaded ? 'loaded' : 'present but not loaded'}
                {typeof model.metadata.dataset_origin === 'string' && `, trained on ${model.metadata.dataset_origin}`}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">No trained models were found.</p>
        )}
        {models.data?.load_warnings.map((warning) => (
          <p key={warning} className="text-sm text-warn">
            {warning}
          </p>
        ))}
      </section>

      <section className="space-y-2" aria-labelledby="refs">
        <h2 id="refs" className="section-title">
          References
        </h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          <li>Westfeld and Pfitzmann (1999), Attacks on Steganographic Systems: the chi-square attack.</li>
          <li>Fridrich, Goljan and Du (2001), Detecting LSB Steganography in Color and Gray-Scale Images: RS analysis.</li>
          <li>Dumitrescu, Wu and Wang (2003), Detection of LSB Steganography via Sample Pair Analysis.</li>
          <li>Mielikäinen (2006), LSB Matching Revisited.</li>
          <li>Pevný, Bas and Fridrich (2010), Steganalysis by Subtractive Pixel Adjacency Matrix.</li>
          <li>Holub, Fridrich and Denemark (2014), Universal Distortion Design for Steganography in an Arbitrary Domain: S-UNIWARD.</li>
          <li>Li, Wang, Huang and Li (2014), A New Cost Function for Spatial Image Steganography: HILL.</li>
          <li>Bas, Filler and Pevný (2011), Break Our Steganographic System: the BOSSbase dataset.</li>
          <li>Boroumand, Chen and Fridrich (2019), Deep Residual Network for Steganalysis of Digital Images.</li>
          <li>RFC 9106 (Argon2), RFC 8032 (Ed25519), NIST SP 800-38D (AES-GCM).</li>
        </ul>
      </section>
    </div>
  );
}
