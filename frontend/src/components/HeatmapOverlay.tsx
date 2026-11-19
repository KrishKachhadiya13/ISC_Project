import { useId, useState } from 'react';

interface Props {
  imageUrl: string;
  gradcamBase64: string | null;
  residualBase64: string | null;
}

/** Image with a CNN explanation map on top; opacity slider and map toggle. */
export function HeatmapOverlay({ imageUrl, gradcamBase64, residualBase64 }: Props) {
  const sliderId = useId();
  const [opacity, setOpacity] = useState(0.55);
  const [kind, setKind] = useState<'gradcam' | 'residual'>(gradcamBase64 ? 'gradcam' : 'residual');
  const source = kind === 'gradcam' ? gradcamBase64 : residualBase64;
  if (!gradcamBase64 && !residualBase64) return null;

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-lg border border-line bg-bg">
        <img src={imageUrl} alt="Scanned image" className="block w-full" />
        {source && (
          <img
            src={`data:image/png;base64,${source}`}
            alt={`${kind === 'gradcam' ? 'Network attention' : 'Fine-grain noise'} heat map overlay`}
            className="absolute inset-0 h-full w-full mix-blend-screen"
            style={{ opacity }}
          />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border border-line p-1" role="group" aria-label="Heatmap type">
          {(['gradcam', 'residual'] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={kind === option}
              disabled={option === 'gradcam' ? !gradcamBase64 : !residualBase64}
              onClick={() => setKind(option)}
              className={`rounded-md px-3 py-1 text-xs font-semibold ${kind === option ? 'bg-accent text-on-accent' : 'text-muted'}`}
            >
              {option === 'gradcam' ? 'Network attention' : 'Fine-grain noise'}
            </button>
          ))}
        </div>
        <label htmlFor={sliderId} className="text-xs text-muted">
          Opacity
        </label>
        <input
          id={sliderId}
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          onChange={(event) => setOpacity(Number(event.target.value))}
          className="w-32 accent-[rgb(var(--accent))]"
        />
      </div>
      <p className="text-xs text-muted">
        These maps show where the neural network responded most strongly (for large images, in the
        highest-scoring 256 × 256 tile) and where the image has the most fine-grain noise. They are
        hints, not proof that data is hidden.
      </p>
    </div>
  );
}
