import { describe, expect, it } from 'vitest';

import { isAdaptive, messageLengthFor } from './ArmsRace';

describe('messageLengthFor', () => {
  it('sizes a plain LSB message from bpp, minus the fixed overhead', () => {
    // 0.4 bpp of a 256x256 image is 26,214 bits; keyed overhead is 104 + 128 + 129*8 = 1,264 bits.
    expect(messageLengthFor(0.4, 256 * 256, 'keyed')).toBe(Math.floor((26214.4 - 1264) / 8));
  });

  it('reserves 64 extra bits for the STC length field on S-UNIWARD and HILL', () => {
    const plain = messageLengthFor(0.4, 256 * 256, 'keyed', 'lsb_replace');
    const adaptive = messageLengthFor(0.4, 256 * 256, 'keyed', 'suniward');
    expect(plain - adaptive).toBe(8);
    expect(messageLengthFor(0.4, 256 * 256, 'keyed', 'hill')).toBe(adaptive);
  });

  it('never returns less than one character', () => {
    expect(messageLengthFor(0.01, 64 * 64, 'keyed', 'hill')).toBe(1);
  });

  it('knows which methods use STC', () => {
    expect(isAdaptive('suniward')).toBe(true);
    expect(isAdaptive('hill')).toBe(true);
    expect(isAdaptive('lsb_match')).toBe(false);
  });
});
