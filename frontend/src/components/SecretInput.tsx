import { Eye, EyeOff } from 'lucide-react';
import { useId, useState } from 'react';

import { MIN_PASSWORD_LENGTH, passwordStrength } from '../lib/password';

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  showStrength?: boolean;
  hint?: string;
  autoComplete?: string;
  required?: boolean;
}

const BAR_COLOURS = ['bg-bad', 'bg-bad', 'bg-warn', 'bg-ok', 'bg-ok'];

export function SecretInput({
  label,
  value,
  onChange,
  showStrength = false,
  hint,
  autoComplete = 'new-password',
  required = false,
}: Props) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const strength = passwordStrength(value);
  return (
    <div>
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          className="field pr-11"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          spellCheck={false}
          required={required}
          aria-describedby={`${id}-hint`}
        />
        <button
          type="button"
          className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-muted hover:text-fg"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? `Hide ${label}` : `Show ${label}`}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
      {showStrength && value && (
        <div className="mt-2" aria-live="polite">
          <div className="flex gap-1" aria-hidden="true">
            {[1, 2, 3, 4].map((step) => (
              <span
                key={step}
                className={`h-1.5 flex-1 rounded-full ${step <= strength.score ? BAR_COLOURS[strength.score] : 'bg-line'}`}
              />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted">
            Strength: <span className="font-semibold text-fg">{strength.label}</span>
            {strength.bits > 0 && ` (~${strength.bits} bits estimated)`}
          </p>
        </div>
      )}
      <p id={`${id}-hint`} className="hint">
        {hint ?? `At least ${MIN_PASSWORD_LENGTH} characters.`}
      </p>
    </div>
  );
}
