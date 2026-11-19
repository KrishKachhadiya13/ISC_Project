import { describe, expect, it } from 'vitest';

import { maxMessageBytes } from '../pages/Hide';
import { base64ToBytes } from './download';
import { groupHex } from './fingerprint';
import { formatBytes, formatNumber, shortHash } from './format';
import { passwordStrength } from './password';
import { bitPlaneRgba, fromRgba, type RawImage } from './pixels';

describe('capacity (Section 6.2)', () => {
  it('matches the backend formula for a 256x256 grayscale keyed cover', () => {
    // (65536 - 128 - 104) / 8 = 8163 packet bytes; minus 128 overhead and 1 kind byte.
    expect(maxMessageBytes(256 * 256, 'keyed')).toBe(8163 - 128 - 1);
  });
  it('sequential mode has no salt bits reserved', () => {
    expect(maxMessageBytes(256 * 256, 'sequential')).toBe(Math.floor((65536 - 104) / 8) - 129);
  });
  it('2-LSB roughly doubles capacity and matches the backend formula', () => {
    // ((65536 - 128) * 2 - 104) / 8 = 16338 packet bytes; minus 128 overhead and 1 kind byte.
    expect(maxMessageBytes(256 * 256, 'keyed', 2)).toBe(Math.floor(((65536 - 128) * 2 - 104) / 8) - 129);
    expect(maxMessageBytes(256 * 256, 'keyed', 2)).toBeGreaterThan(2 * maxMessageBytes(256 * 256, 'keyed', 1));
  });
  it('never goes negative for tiny images', () => {
    expect(maxMessageBytes(100, 'keyed')).toBe(0);
  });
});

describe('format helpers', () => {
  it('formats bytes and numbers', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(0.12345, 2)).toBe('0.12');
  });
  it('shortens hashes and groups hex', () => {
    expect(shortHash('a'.repeat(64), 4)).toBe('aaaa…aaaa');
    expect(groupHex('abcdef0123')).toBe('abcd ef01 23');
  });
});

describe('passwordStrength', () => {
  it('flags short, weak and strong passwords', () => {
    expect(passwordStrength('abc').label).toBe('Too short');
    expect(passwordStrength('aaaaaaaa').score).toBeLessThanOrEqual(1);
    expect(passwordStrength('Correct-Horse-Battery-9!').score).toBe(4);
  });
});

describe('pixels', () => {
  it('detects grayscale RGBA and keeps colour otherwise', () => {
    const gray = fromRgba(new Uint8ClampedArray([5, 5, 5, 255, 9, 9, 9, 255]), 2, 1);
    expect(gray.channels).toBe(1);
    expect(Array.from(gray.samples)).toEqual([5, 9]);
    const colour = fromRgba(new Uint8ClampedArray([5, 6, 7, 255]), 1, 1);
    expect(colour.channels).toBe(3);
  });
  it('extracts the LSB plane as black and white', () => {
    const image: RawImage = { width: 2, height: 1, channels: 1, samples: new Uint8ClampedArray([3, 4]) };
    const plane = bitPlaneRgba(image, 0, 0);
    expect(Array.from(plane.slice(0, 4))).toEqual([255, 255, 255, 255]); // 3 has LSB 1
    expect(Array.from(plane.slice(4, 8))).toEqual([0, 0, 0, 255]); // 4 has LSB 0
    expect(Array.from(bitPlaneRgba(image, 2, 0).slice(0, 8))).toEqual([0, 0, 0, 255, 255, 255, 255, 255]);
  });
  it('decodes base64 byte-exactly', () => {
    expect(Array.from(base64ToBytes(btoa(String.fromCharCode(0, 1, 254, 255))))).toEqual([0, 1, 254, 255]);
  });
});
