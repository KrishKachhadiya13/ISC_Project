import { Check } from 'lucide-react';

export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <nav aria-label="Progress" className="mb-6">
      <ol className="grid grid-cols-4 gap-2">
        {steps.map((step, index) => {
          const done = index < current;
          const active = index === current;
          return (
            <li key={step} aria-current={active ? 'step' : undefined}>
              <div
                className={`h-1.5 rounded-full ${done || active ? 'bg-accent' : 'bg-line'}`}
                aria-hidden="true"
              />
              <p className={`mt-2 flex items-center gap-1 text-xs font-semibold ${active ? 'text-fg' : 'text-muted'}`}>
                {done && <Check className="h-3.5 w-3.5 text-accent" aria-hidden="true" />}
                <span className="hidden sm:inline">{index + 1}. </span>
                {step}
                {done && <span className="sr-only"> (completed)</span>}
              </p>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
