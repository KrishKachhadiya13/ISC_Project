import { useEffect, useRef } from 'react';

/**
 * Bring a freshly produced result into view and move focus to it, so keyboard and screen-reader
 * users land on the answer instead of being left at the button.
 *
 * Pass anything that changes when a new result arrives (for example the mutation data). The
 * element needs tabIndex={-1} so it can take focus.
 */
export function useRevealOnResult<T extends HTMLElement>(result: unknown) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const element = ref.current;
    if (!result || !element) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    element.scrollIntoView?.({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    element.focus({ preventScroll: true });
  }, [result]);
  return ref;
}
