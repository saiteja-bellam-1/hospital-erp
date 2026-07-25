import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '../../lib/utils';

export function Stepper({ steps, activeIndex = 0, onStepClick }) {
  return (
    <ol className="flex gap-2 overflow-x-auto pb-2" aria-label="Setup progress">
      {steps.map((step, index) => {
        const done = !!step.completed;
        const active = index === activeIndex;
        return (
          <li key={step.key} className="flex items-center min-w-fit">
            <button
              type="button"
              onClick={() => onStepClick?.(index)}
              className={cn(
                'flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-colors',
                done && 'border-emerald-200 bg-emerald-50 text-emerald-700',
                active && !done && 'border-blue-300 bg-blue-50 text-blue-700',
                !active && !done && 'border-slate-200 bg-white text-slate-500',
              )}
              aria-current={active ? 'step' : undefined}
            >
              <span className={cn(
                'flex h-5 w-5 items-center justify-center rounded-full text-[11px]',
                done ? 'bg-emerald-600 text-white' : active ? 'bg-blue-600 text-white' : 'bg-slate-100',
              )}>
                {done ? <Check className="h-3 w-3" /> : index + 1}
              </span>
              {step.label}
            </button>
            {index < steps.length - 1 && <span className="mx-1 h-px w-4 bg-slate-200" />}
          </li>
        );
      })}
    </ol>
  );
}
