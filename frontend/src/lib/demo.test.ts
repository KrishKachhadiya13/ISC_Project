import { describe, expect, it, vi } from 'vitest';

import type { Manifest } from '../api/types';
import { DEMO, getDemoArtifacts, isDemoMode, setDemoArtifacts, subscribeDemoArtifacts } from './demo';

describe('presenter mode', () => {
  it('is on only for ?demo=1', () => {
    expect(isDemoMode('?demo=1')).toBe(true);
    expect(isDemoMode('?demo=0')).toBe(false);
    expect(isDemoMode('')).toBe(false);
    expect(isDemoMode('?x=1&demo=1')).toBe(true);
  });

  it('keeps the Hide result in memory and notifies subscribers', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeDemoArtifacts(listener);
    expect(getDemoArtifacts()).toBeNull();
    setDemoArtifacts({
      stego: new Blob([new Uint8Array([1])]),
      manifest: { signature: 'x' } as unknown as Manifest,
      publicKeyPem: 'pem',
      fingerprint: 'abcd',
      method: 'lsb_replace',
      mode: 'keyed',
      coverName: 'c.png',
    });
    expect(getDemoArtifacts()?.fingerprint).toBe('abcd');
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
    setDemoArtifacts(null);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('never uses browser storage for demo data', () => {
    setDemoArtifacts(null);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });

  it('uses passwords long enough for the server minimum', () => {
    expect(DEMO.password.length).toBeGreaterThanOrEqual(8);
    expect(DEMO.keyPassword.length).toBeGreaterThanOrEqual(8);
  });
});
