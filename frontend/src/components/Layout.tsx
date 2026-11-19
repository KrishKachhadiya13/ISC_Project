import { Menu, Moon, Sun, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { useHealth } from '../api/hooks';
import { SITE } from '../lib/project';
import { DemoBanner, useDemoMode } from './DemoTools';
import { Logo } from './Logo';

// Route paths are stable (links in docs and bookmarks keep working); only the labels are plain words.
const NAV = [
  { to: '/hide', label: 'Hide a message' },
  { to: '/extract', label: 'Extract & verify' },
  { to: '/detect', label: 'Detect' },
  { to: '/arms-race', label: 'Compare detectors' },
  { to: '/tamper', label: 'Tamper test' },
  { to: '/batch', label: 'Batch scan' },
  { to: '/how-it-works', label: 'How it works' },
];

type Theme = 'dark' | 'light';

function readTheme(): Theme {
  try {
    return localStorage.getItem('sg-theme') === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('sg-theme', theme);
    } catch {
      // Storage may be blocked; the theme still applies for this visit.
    }
  }, [theme]);
  return [theme, () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))];
}

function ServerStatus() {
  const { isError, isLoading } = useHealth();
  const text = isLoading ? 'Connecting' : isError ? 'Server not reachable' : 'Server connected';
  const colour = isLoading ? 'bg-warn' : isError ? 'bg-bad' : 'bg-ok';
  return (
    <span className="chip px-2.5 2xl:px-3" role="status" title={text}>
      <span className={`h-2 w-2 rounded-full ${colour}`} aria-hidden="true" />
      {/* Full text only where there is room; the coloured dot (and title) cover narrower screens. */}
      <span className="sr-only 2xl:not-sr-only">{text}</span>
    </span>
  );
}

export function Layout() {
  const [theme, toggleTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  useEffect(() => {
    setOpen(false);
    // A new page starts at the top, as a normal website does.
    window.scrollTo?.(0, 0);
  }, [location.pathname]);
  // Keep presenter mode switched on while navigating between pages.
  const demo = useDemoMode();
  const keep = (path: string) => ({ pathname: path, search: demo ? '?demo=1' : '' });

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `whitespace-nowrap rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors ${
      isActive ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-raised hover:text-fg'
    }`;

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent"
      >
        Skip to content
      </a>
      <DemoBanner />
      <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/75 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3 sm:px-6">
          <NavLink to={keep('/')} className="flex items-center gap-2.5" aria-label={`${SITE.name} home`}>
            <Logo />
            <span className="font-display text-lg font-bold tracking-tight">{SITE.name}</span>
          </NavLink>
          <nav aria-label="Main" className="ml-4 hidden flex-1 gap-0.5 xl:flex">
            {NAV.map((item) => (
              <NavLink key={item.to} to={keep(item.to)} className={linkClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ServerStatus />
            <button
              type="button"
              onClick={toggleTheme}
              className="btn-ghost p-2"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            >
              {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
            <button
              type="button"
              className="btn-ghost p-2 xl:hidden"
              aria-expanded={open}
              aria-controls="mobile-nav"
              aria-label={open ? 'Close menu' : 'Open menu'}
              onClick={() => setOpen((current) => !current)}
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        {open && (
          <nav id="mobile-nav" aria-label="Main" className="border-t border-line/70 px-4 py-3 xl:hidden">
            <div className="grid gap-1 sm:grid-cols-2">
              {NAV.map((item) => (
                <NavLink key={item.to} to={keep(item.to)} className={linkClass}>
                  {item.label}
                </NavLink>
              ))}
            </div>
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-10 sm:px-6 sm:py-14">
        <Outlet />
      </main>
      <footer className="mt-8 border-t border-line/70 bg-panel/60">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 text-sm sm:px-6 md:grid-cols-[2fr_1fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <Logo size={28} />
              <span className="font-display text-base font-bold">{SITE.name}</span>
            </div>
            <p className="mt-3 max-w-md text-muted">{SITE.tagline}</p>
          </div>
          <nav aria-label="Footer">
            <p className="eyebrow">Pages</p>
            <ul className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5">
              {[...NAV, { to: '/about', label: 'About' }].map((item) => (
                <li key={item.to}>
                  <NavLink to={keep(item.to)} className="text-muted hover:text-accent">
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </footer>
    </div>
  );
}
