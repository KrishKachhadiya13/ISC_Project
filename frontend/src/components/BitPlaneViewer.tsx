import { useEffect, useId, useRef, useState } from 'react';

import { bitPlane, readPixels, type RawImage } from '../lib/pixels';
import { ErrorBanner, Spinner } from './ui';

/**
 * Show one bit plane of one channel. Plane 0 (the LSB) of a natural image
 * still shows faint structure; after LSB embedding it turns to noise where
 * bits were written — top rows only in sequential mode, everywhere in keyed.
 */
export function BitPlaneViewer({ file }: { file: Blob }) {
  const planeId = useId();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<RawImage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [plane, setPlane] = useState(0);
  const [channel, setChannel] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setImage(null);
    readPixels(file)
      .then((result) => !cancelled && setImage(result))
      .catch((reason: unknown) => !cancelled && setError(reason));
    return () => {
      cancelled = true;
    };
  }, [file]);

  useEffect(() => {
    if (!image || !canvasRef.current) return;
    const canvas = canvasRef.current;
    canvas.width = image.width;
    canvas.height = image.height;
    canvas.getContext('2d')?.putImageData(bitPlane(image, plane, channel), 0, 0);
  }, [image, plane, channel]);

  if (error) return <ErrorBanner error={error} />;
  if (!image) return <Spinner label="Reading pixels…" />;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <label htmlFor={planeId} className="field-label">
            Bit plane: <span className="mono">{plane}</span> {plane === 0 && '(LSB)'}
            {plane === 7 && '(MSB)'}
          </label>
          <input
            id={planeId}
            type="range"
            min={0}
            max={7}
            value={plane}
            onChange={(event) => setPlane(Number(event.target.value))}
            className="w-48 accent-[rgb(var(--accent))]"
          />
        </div>
        {image.channels === 3 && (
          <div className="inline-flex rounded-lg border border-line p-1" role="group" aria-label="Colour channel">
            {['Red', 'Green', 'Blue'].map((name, index) => (
              <button
                key={name}
                type="button"
                aria-pressed={channel === index}
                onClick={() => setChannel(index)}
                className={`rounded-md px-3 py-1 text-xs font-semibold ${channel === index ? 'bg-accent text-on-accent' : 'text-muted'}`}
              >
                {name}
              </button>
            ))}
          </div>
        )}
      </div>
      <canvas
        ref={canvasRef}
        className="w-full rounded-lg border border-line [image-rendering:pixelated]"
        role="img"
        aria-label={`Bit plane ${plane}${image.channels === 3 ? ` of channel ${channel}` : ''}`}
      />
    </div>
  );
}
