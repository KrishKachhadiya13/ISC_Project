import { Presentation } from 'lucide-react';
import { useSyncExternalStore } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  getDemoArtifacts,
  isDemoMode,
  subscribeDemoArtifacts,
  type DemoArtifacts,
} from '../lib/demo';

/** True when the URL has ?demo=1; re-evaluated on navigation. */
export function useDemoMode(): boolean {
  const [params] = useSearchParams();
  return params.get('demo') === '1' || isDemoMode();
}

/** The latest Hide result held in memory, if any. */
export function useDemoArtifacts(): DemoArtifacts | null {
  return useSyncExternalStore(subscribeDemoArtifacts, getDemoArtifacts, getDemoArtifacts);
}

/** Banner reminding the presenter (and audience) that fixed demo values are in use. */
export function DemoBanner() {
  const demo = useDemoMode();
  if (!demo) return null;
  return (
    <div role="status" className="border-b border-violet/40 bg-violet/10 px-4 py-2 text-center text-xs sm:text-sm">
      <Presentation className="mr-1.5 inline h-4 w-4 text-violet" aria-hidden="true" />
      <strong>Presenter mode.</strong> Fixed demo passwords and a throw-away keypair are used. Never enter real
      secrets. Nothing is stored.
    </div>
  );
}

/** One-click helper button shown only in presenter mode. */
export function DemoButton({
  onClick,
  children,
  disabled,
}: {
  onClick: () => void | Promise<void>;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  const demo = useDemoMode();
  if (!demo) return null;
  return (
    <button
      type="button"
      className="btn border border-violet/60 bg-violet/10 text-fg hover:bg-violet/20"
      disabled={disabled}
      onClick={() => void onClick()}
    >
      <Presentation className="h-4 w-4 text-violet" aria-hidden="true" /> {children}
    </button>
  );
}
