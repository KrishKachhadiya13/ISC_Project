/**
 * Presenter mode (`?demo=1`).
 *
 * Makes a live demo one click per step. Everything here is clearly a DEMO:
 * the passwords are fixed, public strings shown on screen, and the keypair
 * is generated fresh by the backend and held only in memory (a module
 * variable, never localStorage or sessionStorage). Never use these values for
 * real secrets.
 */
import type { Manifest, Method, Mode } from '../api/types';

export const DEMO = {
  message: 'Meet at the old bridge at nine. (StegaGuard demo message)',
  password: 'demo-message-password',
  keyPassword: 'demo-key-password',
  // About 1,100 characters. Measured on the live detectors: messages around this size are flagged
  // reliably, while a one-sentence message changes too few pixels to be noticed.
  longMessage: [
    'Meet at the old bridge at nine. Come alone and bring the folder with the blue cover.',
    'The route along the river is closed, so take the footpath behind the market and cross at the second lamp.',
    'If anyone follows you, walk past the bridge and wait at the cafe on the corner until half past.',
    'Do not use your phone near the bridge. Leave it at home or switch it off before you leave.',
    'The documents inside the folder are copies; the originals stay where they are until we have spoken.',
    'You will recognise me by the grey coat and the newspaper under my arm.',
    'We say nothing about names or places until we are sure that nobody is close enough to listen.',
    'After we talk, go home by a different street than the one you came on, and do not look back.',
    'I will send the next message the same way, in a different picture, with a different password.',
    'Delete the picture once you have read this. (StegaGuard demo message, long version.)',
    'This longer text exists so the detectors have enough changed pixels to notice something.',
    'A short sentence changes only a handful of pixels, which is far too little to measure.',
  ].join(' '),
  coverUrl: '/demo/cover.png',
  coverName: 'demo_cover.png',
} as const;

export interface DemoArtifacts {
  stego: Blob;
  manifest: Manifest;
  publicKeyPem: string;
  fingerprint: string;
  method: Method;
  mode: Mode;
  coverName: string;
}

let artifacts: DemoArtifacts | null = null;
const listeners = new Set<() => void>();

export function isDemoMode(search: string = window.location.search): boolean {
  return new URLSearchParams(search).get('demo') === '1';
}

export function getDemoArtifacts(): DemoArtifacts | null {
  return artifacts;
}

export function setDemoArtifacts(next: DemoArtifacts | null): void {
  artifacts = next;
  listeners.forEach((listener) => listener());
}

export function subscribeDemoArtifacts(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Candidate demo covers, best first.
 *
 * `bossbase_01.png` is a held-out BOSSbase test cover copied locally by
 * `python -m scripts.make_demo_assets` (gitignored). It matches what the
 * detectors were trained on. The bundled CC0 photo is a fallback that works
 * for the crypto steps but is a different kind of image, so detectors can
 * misjudge it; the Detect page says so when it is used.
 */
export const DEMO_COVER_CANDIDATES = ['/demo/bossbase_01.png', DEMO.coverUrl] as const;

export interface DemoCover {
  file: File;
  /** True when the in-distribution BOSSbase cover was found. */
  inDistribution: boolean;
}

async function fetchImage(url: string): Promise<Blob | null> {
  try {
    const response = await fetch(url);
    // A single-page app answers unknown paths with index.html (status 200),
    // so the content type must be checked as well.
    if (!response.ok || !(response.headers.get('content-type') ?? '').startsWith('image/')) return null;
    return await response.blob();
  } catch {
    return null;
  }
}

export async function loadDemoCoverInfo(): Promise<DemoCover> {
  for (const [index, url] of DEMO_COVER_CANDIDATES.entries()) {
    const blob = await fetchImage(url);
    if (blob) {
      return {
        file: new File([blob], DEMO.coverName, { type: 'image/png' }),
        inDistribution: index === 0,
      };
    }
  }
  throw new Error('No demo cover image is available.');
}

/** Fetch the best available demo cover. */
export async function loadDemoCover(): Promise<File> {
  return (await loadDemoCoverInfo()).file;
}
