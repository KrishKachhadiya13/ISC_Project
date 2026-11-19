import { useEffect, useRef } from 'react';

const SIZE = 96;

/** Read an `r g b` theme token (e.g. "129 154 255") as numbers. */
function token(name: string): [number, number, number] {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const parts = raw.split(/\s+/).map(Number);
  return [parts[0] ?? 128, parts[1] ?? 128, parts[2] ?? 128];
}

/**
 * Explanatory figure: the lowest bit plane of a smooth image. Untouched pixels form regular
 * stripes; once a message is hidden, that plane becomes random-looking noise. A sweep moves
 * across the picture to show the change. With reduced motion, a still frame is drawn.
 */
export function BitPlaneFigure() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return undefined;
    canvas.width = SIZE;
    canvas.height = SIZE;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const image = context.createImageData(SIZE, SIZE);
    const noise = crypto.getRandomValues(new Uint8Array(SIZE * SIZE));
    let frame = 0;
    let timer = 0;

    const draw = () => {
      const [bgR, bgG, bgB] = token('--raised');
      const [fgR, fgG, fgB] = token('--fg');
      const [acR, acG, acB] = token('--accent');
      // The boundary position, 0..1, sweeping left to right and pausing at both ends.
      const phase = reduce ? 0.5 : Math.min(1, Math.max(0, ((frame % 160) - 20) / 120));
      const boundary = phase * SIZE;
      for (let y = 0; y < SIZE; y += 1) {
        for (let x = 0; x < SIZE; x += 1) {
          const index = y * SIZE + x;
          const embedded = x < boundary;
          const smooth = Math.floor(128 + 60 * Math.sin(x / 9) + 50 * Math.cos(y / 13)) & 1;
          const bit = embedded ? noise[index] & 1 : smooth;
          const offset = index * 4;
          if (bit) {
            // A set bit: tinted with the accent where a message was written, neutral elsewhere.
            image.data[offset] = embedded ? acR * 0.75 + bgR * 0.25 : fgR * 0.55 + bgR * 0.45;
            image.data[offset + 1] = embedded ? acG * 0.75 + bgG * 0.25 : fgG * 0.55 + bgG * 0.45;
            image.data[offset + 2] = embedded ? acB * 0.75 + bgB * 0.25 : fgB * 0.55 + bgB * 0.45;
          } else {
            image.data[offset] = bgR;
            image.data[offset + 1] = bgG;
            image.data[offset + 2] = bgB;
          }
          image.data[offset + 3] = 255;
        }
      }
      context.putImageData(image, 0, 0);
      frame += 1;
    };

    draw();
    if (!reduce) timer = window.setInterval(draw, 50);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <figure className="card overflow-hidden p-3 sm:p-4">
      <div className="mb-3 flex items-center justify-between text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent" aria-hidden="true" /> Message hidden
        </span>
        <span>Untouched image</span>
      </div>
      <canvas
        ref={ref}
        className="aspect-square w-full rounded-lg border border-line [image-rendering:pixelated]"
        role="img"
        aria-label="The lowest bit plane of an image: regular stripes on the right, and random-looking noise on the left where a message has been hidden."
      />
      <figcaption className="mt-3 text-xs leading-relaxed text-muted">
        The lowest bit plane of a picture. Regular stripes are an untouched image; the noise on the
        left is what the plane looks like once a message is hidden in it.
      </figcaption>
    </figure>
  );
}
