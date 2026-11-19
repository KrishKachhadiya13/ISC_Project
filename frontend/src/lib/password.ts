export const MIN_PASSWORD_LENGTH = 8;

export interface Strength {
  score: 0 | 1 | 2 | 3 | 4;
  label: 'Too short' | 'Weak' | 'Fair' | 'Good' | 'Strong';
  bits: number;
}

/**
 * Rough entropy estimate: length × log2(alphabet size).
 *
 * It ignores dictionary words, so it over-estimates passwords like
 * "Password123"; the meter is guidance, while the server enforces only the
 * minimum length.
 */
export function passwordStrength(password: string): Strength {
  if (password.length < MIN_PASSWORD_LENGTH) return { score: 0, label: 'Too short', bits: 0 };
  let alphabet = 0;
  if (/[a-z]/.test(password)) alphabet += 26;
  if (/[A-Z]/.test(password)) alphabet += 26;
  if (/[0-9]/.test(password)) alphabet += 10;
  if (/[^A-Za-z0-9]/.test(password)) alphabet += 33;
  const uniqueRatio = new Set(password).size / password.length;
  const bits = Math.round(password.length * Math.log2(Math.max(alphabet, 2)) * Math.min(1, uniqueRatio + 0.3));
  if (bits < 40) return { score: 1, label: 'Weak', bits };
  if (bits < 60) return { score: 2, label: 'Fair', bits };
  if (bits < 80) return { score: 3, label: 'Good', bits };
  return { score: 4, label: 'Strong', bits };
}
