/**
 * Helpers that turn "the image changed" into something a viewer can check by eye:
 * find a small patch of pixels where the hidden message left the most changes, so the raw
 * values before and after can be shown side by side.
 */
import type { RawImage } from './pixels';

export interface PatchProof {
  /** Top-left corner of the patch, in pixels. */
  x: number;
  y: number;
  size: number;
  /** Which colour channel the numbers come from (0 for grayscale). */
  channel: number;
  /** 1 for a grayscale image, 3 for colour. */
  channels: number;
  /** Row-major sample values, `size * size` long. */
  cover: number[];
  stego: number[];
  /** How many samples in the patch differ. */
  changed: number;
}

function sample(image: RawImage, x: number, y: number, channel: number): number {
  const used = Math.min(channel, image.channels - 1);
  return image.samples[(y * image.width + x) * image.channels + used];
}

/**
 * Find the `size` x `size` window with the most changed samples (the first one wins a tie).
 * Returns null if the images differ in size or are smaller than the window.
 */
export function findBusiestPatch(cover: RawImage, stego: RawImage, size = 8, channel = 0): PatchProof | null {
  if (cover.width !== stego.width || cover.height !== stego.height) return null;
  if (cover.width < size || cover.height < size) return null;
  const { width, height } = cover;

  // Summed-area table of changed samples, so every window count is four lookups.
  const stride = width + 1;
  const sums = new Int32Array(stride * (height + 1));
  for (let y = 0; y < height; y += 1) {
    let rowTotal = 0;
    for (let x = 0; x < width; x += 1) {
      rowTotal += sample(cover, x, y, channel) !== sample(stego, x, y, channel) ? 1 : 0;
      sums[(y + 1) * stride + (x + 1)] = sums[y * stride + (x + 1)] + rowTotal;
    }
  }

  let best = { x: 0, y: 0, count: -1 };
  for (let y = 0; y + size <= height; y += 1) {
    for (let x = 0; x + size <= width; x += 1) {
      const count =
        sums[(y + size) * stride + (x + size)] -
        sums[y * stride + (x + size)] -
        sums[(y + size) * stride + x] +
        sums[y * stride + x];
      if (count > best.count) best = { x, y, count };
    }
  }

  const values = (image: RawImage): number[] => {
    const out: number[] = [];
    for (let dy = 0; dy < size; dy += 1) {
      for (let dx = 0; dx < size; dx += 1) out.push(sample(image, best.x + dx, best.y + dy, channel));
    }
    return out;
  };
  return {
    x: best.x,
    y: best.y,
    size,
    channel: Math.min(channel, cover.channels - 1),
    channels: cover.channels,
    cover: values(cover),
    stego: values(stego),
    changed: best.count,
  };
}

/** A sample as eight binary digits, e.g. 142 -> "10001110". */
export function toBinary(value: number): string {
  return Math.max(0, Math.min(255, Math.round(value))).toString(2).padStart(8, '0');
}

/** Index of the first changed cell in a patch, or -1 when nothing changed. */
export function firstChangedIndex(patch: PatchProof): number {
  return patch.cover.findIndex((value, index) => value !== patch.stego[index]);
}

/** The largest change in the patch, in grey levels. */
export function largestChange(patch: PatchProof): number {
  return patch.cover.reduce((largest, value, index) => Math.max(largest, Math.abs(value - patch.stego[index])), 0);
}

export type ProofMethod = 'lsb_replace' | 'lsb_match' | 'lsb2_replace' | 'suniward' | 'hill';

/** How many of the lowest binary digits differ between two values (0 when equal). */
export function differingDigits(before: number, after: number): number {
  const diff = (before ^ after) & 0xff;
  return diff === 0 ? 0 : 32 - Math.clz32(diff);
}

/**
 * Plain-language explanation of one changed pixel, matched to the hiding method.
 *
 * Replacement overwrites the last binary digit, 2-LSB the last two, and matching moves the
 * value by one so that it is odd or even as needed, which can carry into higher digits.
 */
export function explainChange(method: ProofMethod, before: number, after: number): string {
  const digits = differingDigits(before, after);
  const pair = `${toBinary(before)} and ${toBinary(after)}`;
  if (method === 'lsb_replace') {
    return `In binary that is ${pair}: only the last digit differs. That last digit is where the hidden message lives.`;
  }
  if (method === 'lsb2_replace') {
    return `In binary that is ${pair}: ${
      digits <= 1 ? 'only the last digit' : 'the last two digits'
    } differ. This method stores two message bits in the last two digits of each pixel it uses.`;
  }
  if (method === 'suniward' || method === 'hill') {
    const scheme = method === 'suniward' ? 'S-UNIWARD' : 'HILL';
    return `In binary that is ${pair}. ${scheme} with STC changes selected pixels by one grey level, favoring places that its cost map estimates will be less noticeable.`;
  }
  const moved = after > before ? 'up' : 'down';
  return `In binary that is ${pair}. This method stores each message bit in whether a pixel value is odd or even, and moves the pixel ${moved} by one when it needs to flip that.${
    digits > 1 ? ` Here the move carried into ${digits} digits, which is why matching leaves a harder-to-spot trace than replacement.` : ''
  }`;
}

