import { describe, expect, it } from 'vitest';

import type { Stage } from '../api/types';
import { explainFailure } from './receive';

const stage = (name: string, status: Stage['status'], code: string | null = null): Stage => ({ name, status, detail: 'detail', code });

describe('explainFailure', () => {
  it('returns null when nothing failed', () => {
    expect(explainFailure([stage('read_image', 'passed')])).toBeNull();
  });

  it('treats a missing message and a wrong password as the same case', () => {
    const reason = explainFailure([stage('read_image', 'passed'), stage('extract_bits', 'failed', 'NO_HIDDEN_DATA')]);
    expect(reason?.title).toBe('No hidden message found');
    expect(reason?.text).toContain('password');
  });

  it('distinguishes a different sender from a tampered image', () => {
    expect(explainFailure([stage('check_sender', 'failed', 'KEY_MISMATCH')])?.title).toBe('Signed by someone else');
    expect(explainFailure([stage('verify_signature', 'failed', 'VERIFICATION_FAILED')])?.title).toBe('The signature does not match');
  });

  it('only blames the password when the signature already passed', () => {
    expect(
      explainFailure([stage('verify_signature', 'passed'), stage('derive_key_and_decrypt', 'failed', 'DECRYPTION_FAILED')])?.title,
    ).toBe('The message password is wrong');
  });
});
