import { AlertTriangle, CheckCircle2, CircleSlash, Info, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';

import { ApiError } from '../api/client';

type Tone = 'ok' | 'bad' | 'warn' | 'info' | 'neutral';

const TONE_CLASSES: Record<Tone, string> = {
  ok: 'border-ok/40 bg-ok/10 text-ok',
  bad: 'border-bad/40 bg-bad/10 text-bad',
  warn: 'border-warn/40 bg-warn/10 text-warn',
  info: 'border-accent/40 bg-accent/10 text-accent',
  neutral: 'border-line bg-raised text-muted',
};

const TONE_ICONS: Record<Tone, typeof Info> = {
  ok: CheckCircle2,
  bad: XCircle,
  warn: AlertTriangle,
  info: Info,
  neutral: CircleSlash,
};

/** Status pill: colour is always paired with an icon and words. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  const Icon = TONE_ICONS[tone];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${TONE_CLASSES[tone]}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {children}
    </span>
  );
}

export function Callout({
  tone = 'info',
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
}) {
  const Icon = TONE_ICONS[tone];
  return (
    <div className={`flex gap-3 rounded-lg border border-l-4 p-3.5 text-sm ${TONE_CLASSES[tone]}`} role="note">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="text-fg">
        {title && <p className="font-semibold">{title}</p>}
        <div className="text-fg/90">{children}</div>
      </div>
    </div>
  );
}

const FRIENDLY: Partial<Record<string, string>> = {
  NETWORK: 'The backend is not reachable. Is it running on port 8000?',
  RATE_LIMITED: 'Too many requests in a short time. Please wait a moment and retry.',
  IMAGE_TOO_LARGE: 'That image is too large for this operation.',
  UNSUPPORTED_FORMAT: 'That image format cannot be used here.',
  STC_UNAVAILABLE: 'S-UNIWARD and HILL are switched off on this server until its optional STC package is installed. The other hiding methods still work.',
};

/** Accessible error banner for any thrown value (API errors keep their code). */
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const isApi = error instanceof ApiError;
  const message = isApi ? error.message : error instanceof Error ? error.message : String(error);
  const hint = isApi ? FRIENDLY[error.code] : undefined;
  return (
    <div role="alert" className="flex gap-3 rounded-lg border border-bad/50 bg-bad/10 p-3.5 text-sm">
      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-bad" aria-hidden="true" />
      <div>
        <p className="font-semibold text-bad">
          {isApi ? error.code.replace(/_/g, ' ') : 'Something went wrong'}
        </p>
        <p className="text-fg/90">{message}</p>
        {hint && hint !== message && <p className="mt-1 text-muted">{hint}</p>}
      </div>
    </div>
  );
}

export function MetricCard({
  label,
  value,
  unit,
  hint,
}: {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-line/80 bg-panel/70 p-4" title={hint}>
      <p className="eyebrow">{label}</p>
      <p className="mono mt-1 text-2xl font-medium text-fg">
        {value}
        {unit && <span className="ml-1 text-sm font-medium text-muted">{unit}</span>}
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2" role="status">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        aria-hidden="true"
      />
      <span>{label}</span>
    </span>
  );
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-raised ${className}`} aria-hidden="true" />;
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center">
      <p className="font-semibold text-fg">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="mb-8 border-b border-line/70 pb-6">
      <span className="mb-4 block h-1 w-12 rounded-full bg-accent" aria-hidden="true" />
      <h1 className="page-title">{title}</h1>
      {children && <p className="mt-3 max-w-3xl text-base text-muted">{children}</p>}
    </header>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; hint?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <fieldset>
      <legend className="field-label">{label}</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {options.map((option) => (
          <label
            key={option.value}
            className={`cursor-pointer rounded-lg border p-3 text-sm transition-colors ${
              value === option.value ? 'border-accent bg-accent/10' : 'border-line hover:border-accent/50'
            }`}
          >
            <input
              type="radio"
              className="sr-only"
              name={label}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
            />
            <span className="font-semibold text-fg">{option.label}</span>
            {option.hint && <span className="mt-0.5 block text-xs text-muted">{option.hint}</span>}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
