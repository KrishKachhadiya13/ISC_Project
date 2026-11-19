import { Upload } from 'lucide-react';
import { useEffect, useId, useState } from 'react';

import { publicKeyFingerprint } from '../lib/fingerprint';

interface Props {
  label: string;
  value: string;
  onChange: (pem: string) => void;
  kind: 'public' | 'private';
}

/** Paste or load a PEM key. Public keys show their fingerprint for comparison. */
export function KeyInput({ label, value, onChange, kind }: Props) {
  const id = useId();
  const [fingerprint, setFingerprint] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (kind !== 'public' || !value.trim()) {
      setFingerprint(null);
      return undefined;
    }
    void publicKeyFingerprint(value).then((result) => {
      if (!cancelled) setFingerprint(result);
    });
    return () => {
      cancelled = true;
    };
  }, [kind, value]);

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <label className="btn-ghost cursor-pointer px-2 py-1 text-xs">
          <Upload className="h-3.5 w-3.5" aria-hidden="true" /> Load .pem
          <input
            type="file"
            accept=".pem,.txt,application/x-pem-file"
            className="sr-only"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (file) onChange(await file.text());
              event.target.value = '';
            }}
          />
        </label>
      </div>
      <textarea
        id={id}
        className="field mono h-28 resize-y text-xs"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={
          kind === 'public' ? '-----BEGIN PUBLIC KEY-----' : '-----BEGIN ENCRYPTED PRIVATE KEY-----'
        }
        spellCheck={false}
        autoComplete="off"
      />
      {kind === 'public' && value.trim() && (
        <p className="hint" aria-live="polite">
          {fingerprint ? (
            <>
              Fingerprint: <span className="mono break-all text-fg">{fingerprint}</span>
              <br />
              Compare it with the sender&apos;s copy received through another channel.
            </>
          ) : (
            <span className="text-bad">Not a valid Ed25519 public key PEM.</span>
          )}
        </p>
      )}
    </div>
  );
}
