import { describe, expect, it } from 'vitest';

import type { CheckResult, ExtractResult, Stage, VerifyResult } from '../api/types';
import { verdictWords } from '../lib/format';
import { describeOutcome, type LabOutcome } from './TamperLab';

const check = (ok: boolean): CheckResult => ({ ok, detail: 'detail' });
const stage = (name: string, status: Stage['status'], code: string | null = null): Stage => ({ name, status, detail: 'detail', code });

function outcome(verified: boolean, stages: Stage[], pixelOk: boolean | null): LabOutcome {
  const extract = { stages, verified, plaintext: null, file_base64: null, filename: null, technique: null, mode: null, supplied_key_fingerprint: 'x' } as ExtractResult;
  const verify =
    pixelOk === null
      ? null
      : ({
          overall_ok: pixelOk,
          checks: { pixel_hash: check(pixelOk), manifest_signature: check(true), payload_signature: check(true) },
        } as unknown as VerifyResult);
  return { attacked: new Blob(), extract, verify };
}

describe('describeOutcome', () => {
  it('says the message survived but the image was altered when only the pixel check fails', () => {
    const result = describeOutcome(outcome(true, [stage('verify_signature', 'passed')], false));
    expect(result.tone).toBe('warn');
    expect(result.headline).toContain('image was altered');
  });

  it('reports an intact message when every check passes', () => {
    const result = describeOutcome(outcome(true, [stage('verify_signature', 'passed')], true));
    expect(result.tone).toBe('ok');
    expect(result.text).toBe('Every check passed.');
  });

  it('asks for the manifest when none was loaded', () => {
    expect(describeOutcome(outcome(true, [stage('verify_signature', 'passed')], null)).text).toContain('Load the manifest');
  });

  it('explains a lost message in plain words without a raw code', () => {
    const result = describeOutcome(outcome(false, [stage('extract_bits', 'failed', 'NO_HIDDEN_DATA')], false));
    expect(result.tone).toBe('bad');
    expect(result.headline).toBe('No hidden message found');
    expect(`${result.headline} ${result.text}`).not.toContain('NO_HIDDEN_DATA');
  });
});

describe('verdictWords', () => {
  it('uses the same two phrases on every page', () => {
    expect(verdictWords('suspected_stego')).toBe('Hidden data suspected');
    expect(verdictWords('clean')).toBe('Not flagged');
  });
});
