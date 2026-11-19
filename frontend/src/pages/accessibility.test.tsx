/**
 * Automated WCAG checks with axe-core (installed from npm, run in jsdom).
 *
 * jsdom has no layout engine, so colour contrast cannot be measured here; the
 * theme tokens are checked separately (see docs/DECISIONS.md). These tests
 * catch structural problems: missing labels, bad ARIA, duplicate ids, missing
 * names on buttons and links, table headers, and landmark misuse.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import { App } from '../App';

const PAGES = [
  '/',
  '/hide',
  '/extract',
  '/detect',
  '/arms-race',
  '/tamper',
  '/batch',
  '/how-it-works',
  '/about',
  '/hide?demo=1',
];

beforeAll(() => {
  // No backend in tests: every request fails like an offline server.
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
  // Recharts measures its container; give it a size so charts render.
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

async function violationsFor(path: string): Promise<string[]> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { container, unmount } = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await new Promise((resolve) => setTimeout(resolve, 50));
  // Guard against a vacuous pass: the page must actually have rendered its heading.
  expect(container.querySelector('h1')).not.toBeNull();
  const result = await axe.run(container, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] },
    rules: {
      'color-contrast': { enabled: false }, // not measurable without layout
      region: { enabled: false }, // the router renders inside a test container, not a full page
    },
  });
  unmount();
  return result.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact}): ${violation.help} -> ${violation.nodes
        .slice(0, 2)
        .map((node) => node.target.join(' '))
        .join(' | ')}`,
  );
}

describe('accessibility (axe-core)', () => {
  it.each(PAGES)('%s has no structural WCAG violations', async (path) => {
    expect(await violationsFor(path)).toEqual([]);
  });
});
