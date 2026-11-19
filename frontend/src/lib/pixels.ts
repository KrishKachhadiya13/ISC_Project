/**
 * Read exact pixel values in the browser and re-encode them losslessly.
 *
 * Used for analysis views (bit planes) and the Tamper Lab only — never for
 * downloading a stego image. `colorSpaceConversion: 'none'` stops the browser
 * from colour-managing the decode, so the values match the file.
 */

export interface RawImage {
  width: number;
  height: number;
  /** 1 for grayscale, 3 for RGB. Samples are interleaved row by row. */
  channels: 1 | 3;
  samples: Uint8ClampedArray;
}

export async function readPixels(blob: Blob): Promise<RawImage> {
  const bitmap = await createImageBitmap(blob, {
    colorSpaceConversion: 'none',
    premultiplyAlpha: 'none',
  });
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Canvas 2D is not available in this browser.');
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
  return fromRgba(rgba, canvas.width, canvas.height);
}

/** Collapse RGBA to grayscale when every pixel has R = G = B, else to RGB. */
export function fromRgba(rgba: Uint8ClampedArray, width: number, height: number): RawImage {
  const count = width * height;
  let gray = true;
  for (let index = 0; index < count && gray; index += 1) {
    const offset = index * 4;
    gray = rgba[offset] === rgba[offset + 1] && rgba[offset] === rgba[offset + 2];
  }
  const channels: 1 | 3 = gray ? 1 : 3;
  const samples = new Uint8ClampedArray(count * channels);
  for (let index = 0; index < count; index += 1) {
    for (let channel = 0; channel < channels; channel += 1) {
      samples[index * channels + channel] = rgba[index * 4 + channel];
    }
  }
  return { width, height, channels, samples };
}

/**
 * How many samples per pixel the backend will use for this file.
 *
 * The backend keeps grayscale ("L") images as one channel and turns every
 * other PNG colour type (RGB, palette, grey+alpha, RGBA) into RGB. Pixel
 * values alone cannot tell an RGB file with equal channels from a gray one,
 * so PNG files are classified from the IHDR colour-type byte.
 */
export async function backendChannels(file: Blob, decoded: RawImage): Promise<1 | 3> {
  const header = new Uint8Array(await file.slice(0, 26).arrayBuffer());
  const isPng = header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4e && header[3] === 0x47;
  if (isPng) return header[25] === 0 ? 1 : 3; // colour type 0 = grayscale
  const isPgm = header[0] === 0x50 && (header[1] === 0x35 || header[1] === 0x32);
  if (isPgm) return 1;
  return decoded.channels;
}

export function toImageData(image: RawImage): ImageData {
  const rgba = new Uint8ClampedArray(image.width * image.height * 4);
  for (let index = 0; index < image.width * image.height; index += 1) {
    for (let channel = 0; channel < 3; channel += 1) {
      rgba[index * 4 + channel] = image.samples[index * image.channels + (image.channels === 1 ? 0 : channel)];
    }
    rgba[index * 4 + 3] = 255;
  }
  return new ImageData(rgba, image.width, image.height);
}

/**
 * Bit plane `plane` (0 = LSB) of one channel as a black/white ImageData.
 * LSB embedding turns plane 0 into noise where data was written.
 */
export function bitPlane(image: RawImage, plane: number, channel: number): ImageData {
  return new ImageData(bitPlaneRgba(image, plane, channel), image.width, image.height);
}

/** Pure part of `bitPlane`: RGBA bytes, so it can be tested without a browser. */
export function bitPlaneRgba(image: RawImage, plane: number, channel: number): Uint8ClampedArray {
  const rgba = new Uint8ClampedArray(image.width * image.height * 4);
  const source = Math.min(channel, image.channels - 1);
  for (let index = 0; index < image.width * image.height; index += 1) {
    const bit = (image.samples[index * image.channels + source] >> plane) & 1;
    const value = bit ? 255 : 0;
    rgba[index * 4] = value;
    rgba[index * 4 + 1] = value;
    rgba[index * 4 + 2] = value;
    rgba[index * 4 + 3] = 255;
  }
  return rgba;
}

// ---- Minimal PNG encoder (8-bit grayscale or RGB, no filtering) ----

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.length);
  for (let index = 0; index < 4; index += 1) out[4 + index] = type.charCodeAt(index);
  out.set(data, 8);
  view.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length)));
  return out;
}

async function zlibDeflate(data: Uint8Array): Promise<Uint8Array> {
  // 'deflate' in CompressionStream is the zlib format PNG requires.
  const stream = new Blob([data]).stream().pipeThrough(new CompressionStream('deflate'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/**
 * Encode samples as a PNG without altering any value. This keeps a
 * grayscale stego image grayscale, so a one-pixel edit changes exactly one
 * sample — the point of the Tamper Lab's lossless attacks.
 */
export async function encodePng(image: RawImage): Promise<Blob> {
  const rowLength = image.width * image.channels;
  const raw = new Uint8Array((rowLength + 1) * image.height);
  for (let row = 0; row < image.height; row += 1) {
    raw[row * (rowLength + 1)] = 0; // filter type 0 (None)
    raw.set(image.samples.subarray(row * rowLength, (row + 1) * rowLength), row * (rowLength + 1) + 1);
  }
  const header = new Uint8Array(13);
  const view = new DataView(header.buffer);
  view.setUint32(0, image.width);
  view.setUint32(4, image.height);
  header[8] = 8; // bit depth
  header[9] = image.channels === 1 ? 0 : 2; // colour type: gray or truecolour
  const signature = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]);
  const parts = [
    signature,
    chunk('IHDR', header),
    chunk('IDAT', await zlibDeflate(raw)),
    chunk('IEND', new Uint8Array()),
  ];
  return new Blob(parts, { type: 'image/png' });
}

export function cloneImage(image: RawImage): RawImage {
  return { ...image, samples: new Uint8ClampedArray(image.samples) };
}
