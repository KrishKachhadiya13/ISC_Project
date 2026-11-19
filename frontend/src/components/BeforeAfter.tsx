import { useId, useState } from 'react';

/** Drag a divider between cover and stego. They should look identical. */
export function BeforeAfter({ beforeUrl, afterUrl }: { beforeUrl: string; afterUrl: string }) {
  const id = useId();
  const [split, setSplit] = useState(50);
  return (
    <div>
      <div className="relative overflow-hidden rounded-lg border border-line">
        <img src={afterUrl} alt="Stego image (after embedding)" className="block w-full" />
        <img
          src={beforeUrl}
          alt="Cover image (before embedding)"
          className="absolute inset-0 h-full w-full object-cover"
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
        />
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${split}%` }} />
        <span className="absolute left-2 top-2 rounded bg-bg/80 px-2 py-0.5 text-xs font-semibold">Cover</span>
        <span className="absolute right-2 top-2 rounded bg-bg/80 px-2 py-0.5 text-xs font-semibold">Stego</span>
      </div>
      <label htmlFor={id} className="sr-only">
        Comparison divider position
      </label>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        value={split}
        onChange={(event) => setSplit(Number(event.target.value))}
        className="mt-2 w-full accent-[rgb(var(--accent))]"
      />
    </div>
  );
}
