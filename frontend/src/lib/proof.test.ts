import { describe, expect, it } from 'vitest';

import { differingDigits, explainChange, findBusiestPatch, firstChangedIndex, largestChange, toBinary } from './proof';
import type { RawImage } from './pixels';

function gray(width: number, height: number, fill = 100): RawImage {
  return { width, height, channels: 1, samples: new Uint8ClampedArray(width * height).fill(fill) };
}

describe('findBusiestPatch', () => {
  it('locates the window holding the changes and reports both sets of values', () => {
    const cover = gray(24, 24);
    const stego = gray(24, 24);
    // Change a 3x3 block starting at (10, 12): the busiest 8x8 window must contain all nine.
    for (let dy = 0; dy < 3; dy += 1) for (let dx = 0; dx < 3; dx += 1) stego.samples[(12 + dy) * 24 + (10 + dx)] = 101;
    const patch = findBusiestPatch(cover, stego);
    expect(patch).not.toBeNull();
    expect(patch?.changed).toBe(9);
    expect(patch?.cover).toHaveLength(64);
    expect(patch && patch.x <= 10 && patch.x + 8 >= 13 && patch.y <= 12 && patch.y + 8 >= 15).toBe(true);
    expect(patch?.cover.every((value) => value === 100)).toBe(true);
    expect(patch?.stego.filter((value) => value === 101)).toHaveLength(9);
  });

  it('counts only the chosen channel of an RGB image', () => {
    const rgb = (value: number): RawImage => ({ width: 8, height: 8, channels: 3, samples: new Uint8ClampedArray(8 * 8 * 3).fill(value) });
    const cover = rgb(50);
    const stego = rgb(50);
    stego.samples[(2 * 8 + 3) * 3 + 1] = 51; // green only
    expect(findBusiestPatch(cover, stego, 8, 0)?.changed).toBe(0);
    expect(findBusiestPatch(cover, stego, 8, 1)?.changed).toBe(1);
  });

  it('returns null for mismatched or too-small images', () => {
    expect(findBusiestPatch(gray(16, 16), gray(8, 8))).toBeNull();
    expect(findBusiestPatch(gray(4, 4), gray(4, 4))).toBeNull();
  });

  it('reports zero changes for identical images', () => {
    expect(findBusiestPatch(gray(16, 16), gray(16, 16))?.changed).toBe(0);
  });
});

describe('bit helpers', () => {
  it('writes eight binary digits', () => {
    expect(toBinary(142)).toBe('10001110');
    expect(toBinary(0)).toBe('00000000');
    expect(toBinary(255)).toBe('11111111');
    expect(toBinary(300)).toBe('11111111');
  });

  it('finds the first changed cell and the largest change', () => {
    const patch = { x: 0, y: 0, size: 2, channel: 0, channels: 1, cover: [5, 6, 7, 8], stego: [5, 7, 7, 5], changed: 2 };
    expect(firstChangedIndex(patch)).toBe(1);
    expect(largestChange(patch)).toBe(3);
    expect(firstChangedIndex({ ...patch, stego: patch.cover })).toBe(-1);
  });
});

describe('explainChange', () => {
  it('counts how many binary digits differ', () => {
    expect(differingDigits(182, 183)).toBe(1);
    expect(differingDigits(182, 181)).toBe(2); // 10110110 vs 10110101
    expect(differingDigits(143, 144)).toBe(5); // 10001111 vs 10010000
    expect(differingDigits(7, 7)).toBe(0);
  });

  it('says only the last digit changes for replacement', () => {
    expect(explainChange('lsb_replace', 182, 183)).toContain('only the last digit differs');
  });

  it('describes two digits for 2-LSB', () => {
    expect(explainChange('lsb2_replace', 182, 181)).toContain('the last two digits');
    expect(explainChange('lsb2_replace', 182, 183)).toContain('only the last digit');
  });

  it('explains content-adaptive STC methods by name', () => {
    expect(explainChange('suniward', 100, 101)).toContain('S-UNIWARD with STC');
    expect(explainChange('hill', 100, 101)).toContain('HILL with STC');
  });

  it('does not claim a single digit for matching, and mentions a carry when one happens', () => {
    const carried = explainChange('lsb_match', 143, 144);
    expect(carried).toContain('moves the pixel up by one');
    expect(carried).toContain('carried into 5 digits');
    expect(carried).not.toContain('only the last digit');
    const simple = explainChange('lsb_match', 144, 143);
    expect(simple).toContain('down by one');
  });
});

