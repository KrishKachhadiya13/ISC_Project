import type { CheckResult } from '../api/types';
import { Badge } from './ui';

/** One manifest check with a plain-language name, its reason, and a Pass / Fail word. */
export function CheckRow({ label, check }: { label: string; check: CheckResult | null }) {
  const tone = check?.ok === true ? 'ok' : check?.ok === false ? 'bad' : 'neutral';
  const word = check?.ok === true ? 'Pass' : check?.ok === false ? 'Fail' : 'Not checked';
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-line p-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-xs text-muted">{check?.detail ?? 'Not checked.'}</p>
      </div>
      <Badge tone={tone}>{word}</Badge>
    </div>
  );
}

/** The three manifest checks in the order and wording used on every page that shows them. */
export const CHECK_LABELS = {
  pixel_hash: 'No pixel was changed since signing',
  manifest_signature: 'The sender signed these details',
  payload_signature: 'The sender signed the hidden message',
} as const;
