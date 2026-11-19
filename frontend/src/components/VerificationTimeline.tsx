import { motion, useReducedMotion } from 'framer-motion';
import { CheckCircle2, SkipForward, XCircle } from 'lucide-react';

import type { Stage } from '../api/types';
import { STAGE_LABELS } from '../lib/format';

const STATUS_TEXT = { passed: 'Passed', failed: 'Failed', skipped: 'Skipped' } as const;

/** Ordered receiver stages; each shows an icon, a word and the reason. */
export function VerificationTimeline({ stages, showCodes = true }: { stages: Stage[]; showCodes?: boolean }) {
  const reduceMotion = useReducedMotion();
  return (
    <ol className="relative space-y-3" aria-label="Verification stages">
      {stages.map((stage, index) => {
        const Icon =
          stage.status === 'passed' ? CheckCircle2 : stage.status === 'failed' ? XCircle : SkipForward;
        const tone =
          stage.status === 'passed'
            ? 'border-ok/40 text-ok'
            : stage.status === 'failed'
              ? 'border-bad/60 text-bad bg-bad/10'
              : 'border-line text-muted';
        return (
          <motion.li
            key={stage.name}
            initial={reduceMotion ? false : { opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: reduceMotion ? 0 : index * 0.18 }}
            className={`flex gap-3 rounded-lg border p-3 ${tone}`}
          >
            <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-fg">
                {index + 1}. {STAGE_LABELS[stage.name] ?? stage.name}{' '}
                <span className="font-medium">— {STATUS_TEXT[stage.status]}</span>
                {showCodes && stage.code && <span className="mono ml-2 text-xs">[{stage.code}]</span>}
              </p>
              <p className="text-xs text-muted">{stage.detail}</p>
            </div>
          </motion.li>
        );
      })}
    </ol>
  );
}
