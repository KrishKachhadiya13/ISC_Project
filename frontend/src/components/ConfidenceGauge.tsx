interface Props {
  /** Score in [0, 1]: the estimated probability that the image hides data. */
  value: number;
  /** Scores at or above this value are treated as "hidden data suspected". */
  threshold: number;
  label: string;
}

/**
 * A plain horizontal score bar with the decision threshold marked on it.
 * The number and the explanation are always shown as text; colour is only a second cue.
 */
export function ConfidenceGauge({ value, threshold, label }: Props) {
  const clamped = Math.min(1, Math.max(0, value));
  const flagged = clamped >= threshold;
  return (
    <figure className="w-full" aria-label={`${label}: ${(clamped * 100).toFixed(1)} percent`}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="mono text-4xl font-medium">{(clamped * 100).toFixed(1)}%</span>
        <span className="text-right text-sm text-muted">{label}</span>
      </div>
      <div className="relative mt-3 h-3 border border-line bg-raised" aria-hidden="true">
        <div
          className={`h-full transition-[width] duration-500 ${flagged ? 'bg-bad' : 'bg-ok'}`}
          style={{ width: `${clamped * 100}%` }}
        />
        <div
          className="absolute -top-1 bottom-[-4px] w-0.5 bg-fg"
          style={{ left: `calc(${threshold * 100}% - 1px)` }}
        />
      </div>
      <figcaption className="mt-2 text-xs text-muted">
        The marker shows the flagging line. A score at or beyond it is treated as &ldquo;hidden data
        suspected&rdquo;.
      </figcaption>
    </figure>
  );
}
