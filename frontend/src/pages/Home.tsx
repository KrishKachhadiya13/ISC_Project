import { ArrowRight, EyeOff, Lock, ScanSearch } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useModels } from '../api/hooks';
import { BitPlaneFigure } from '../components/BitPlaneFigure';
import { Reveal } from '../components/Reveal';
import { SITE } from '../lib/project';

const STEPS = [
  { title: 'Encrypt', text: 'The message is locked with a key made from a password.' },
  { title: 'Sign', text: 'The sender signs the package so its origin can be proven.' },
  { title: 'Hide', text: 'The package is written into the lowest bits of an image.' },
  { title: 'Verify', text: 'The receiver checks the signature before anything else.' },
  { title: 'Decrypt', text: 'Only a valid package is ever decrypted.' },
];

const PARTS: { subject: string; title: string; text: string; to: string; cta: string; icon: ReactNode }[] = [
  {
    subject: 'Steganography',
    title: 'Hiding a message',
    text: 'A short message is concealed in the least significant bits of an image so the picture looks unchanged. Several variants are included, and a key can scatter the hidden bits across the image instead of writing them in order.',
    to: '/hide',
    cta: 'Hide a message',
    icon: <EyeOff className="h-5 w-5" />,
  },
  {
    subject: 'Cryptography',
    title: 'Protecting it',
    text: 'Before hiding, the message is encrypted with a password and digitally signed. The receiver checks the signature first and decrypts only if it is valid, so a forged or altered image is rejected before any decryption is attempted.',
    to: '/extract',
    cta: 'Extract and verify',
    icon: <Lock className="h-5 w-5" />,
  },
  {
    subject: 'Steganalysis',
    title: 'Detecting it',
    text: 'Statistical tests and two trained models examine an image and estimate whether it hides data. They are strong on plain least-significant-bit hiding and much weaker on more advanced schemes.',
    to: '/detect',
    cta: 'Scan an image',
    icon: <ScanSearch className="h-5 w-5" />,
  },
];

function IconTile({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-accent/30 bg-accent/10 text-accent">
      {children}
    </span>
  );
}

function Status({ label, state }: { label: string; state: string }) {
  const ok = state === 'trained' || state === 'available';
  return (
    <li className="chip">
      <span className={`h-2 w-2 rounded-full ${ok ? 'bg-ok' : 'bg-line'}`} aria-hidden="true" />
      <span className="text-fg">{label}</span>
      <span>{state}</span>
    </li>
  );
}

export function Home() {
  const models = useModels();
  const detectors = models.data?.detectors;
  const stateOf = (trained: boolean | undefined) => (detectors ? (trained ? 'trained' : 'not trained') : 'checking');
  return (
    <div className="space-y-20">
      <section className="relative">
        <div className="bg-grid pointer-events-none absolute -inset-x-4 -top-14 bottom-0 -z-10 sm:-inset-x-6" aria-hidden="true" />
        <div className="grid items-center gap-10 lg:grid-cols-[1.35fr_1fr]">
          <div>
            <p className="chip">
              <span className="h-2 w-2 rounded-full bg-violet" aria-hidden="true" />
              Steganography &middot; cryptography &middot; detection
            </p>
            <h1 className="mt-5 font-display text-5xl font-extrabold tracking-tight sm:text-6xl">{SITE.name}</h1>
            <p className="mt-3 font-display text-xl font-semibold text-muted sm:text-2xl">{SITE.tagline}</p>
            <p className="mt-6 max-w-2xl text-base text-fg/90">
              StegaGuard hides a message inside an ordinary picture, lets the receiver prove who sent it and
              that it was not changed on the way, and scans any image to estimate whether it is hiding
              something. Every step can be tried here.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link to={{ pathname: '/hide', search: '?demo=1' }} className="btn-primary">
                Try the demonstration <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
              <Link to="/how-it-works" className="btn-secondary">
                Read how it works
              </Link>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-4 border-t border-line/70 pt-6">
              {[
                ['5', 'hiding techniques'],
                ['3', 'detectors'],
                ['6', 'verification steps'],
              ].map(([value, label]) => (
                <div key={label}>
                  <dd className="font-display text-3xl font-extrabold text-accent">{value}</dd>
                  <dt className="text-xs text-muted">{label}</dt>
                </div>
              ))}
            </dl>
          </div>
          <BitPlaneFigure />
        </div>
      </section>

      <Reveal>
        <section aria-labelledby="journey">
          <p className="eyebrow">The path of a message</p>
          <h2 id="journey" className="section-title mt-2">
            From password to hidden picture and back
          </h2>
          <ol className="mt-8 grid gap-6 md:grid-cols-5">
            {STEPS.map((step, index) => (
              <li key={step.title} className="relative">
                {index < STEPS.length - 1 && (
                  <span className="absolute left-12 top-5 hidden h-px w-[calc(100%-2rem)] bg-gradient-to-r from-line to-transparent md:block" aria-hidden="true" />
                )}
                <span className="flex h-10 w-10 items-center justify-center rounded-full border border-accent/40 bg-accent/10 font-display text-sm font-bold text-accent">
                  {index + 1}
                </span>
                <h3 className="mt-3 text-base font-bold">{step.title}</h3>
                <p className="mt-1 text-sm text-muted">{step.text}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 text-sm text-muted">
            At any point a defender can scan the image and estimate whether it hides anything. That is the
            third part.
          </p>
        </section>
      </Reveal>

      <Reveal>
        <section aria-labelledby="parts">
          <p className="eyebrow">Three parts</p>
          <h2 id="parts" className="section-title mt-2">
            What it does
          </h2>
          <div className="mt-8 grid gap-5 md:grid-cols-3">
            {PARTS.map((part) => (
              <article key={part.title} className="card card-hover flex flex-col">
                <IconTile>{part.icon}</IconTile>
                <p className="eyebrow mt-5">{part.subject}</p>
                <h3 className="mt-1 text-lg font-bold">{part.title}</h3>
                <p className="mt-2 flex-1 text-sm text-muted">{part.text}</p>
                <Link to={part.to} className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline">
                  {part.cta} <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </article>
            ))}
          </div>
        </section>
      </Reveal>

      <Reveal>
        <section aria-labelledby="detectors" className="max-w-2xl">
          <h2 id="detectors" className="section-title">
            Detectors on this server
          </h2>
          <ul className="mt-4 flex flex-wrap gap-3">
            <Status label="Statistical tests" state="available" />
            <Status label="Feature-based classifier" state={stateOf(detectors?.rf.trained)} />
            <Status label="Neural network" state={stateOf(detectors?.cnn.trained)} />
          </ul>
        </section>
      </Reveal>
    </div>
  );
}
