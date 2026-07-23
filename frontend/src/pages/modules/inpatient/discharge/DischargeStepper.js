import React from 'react';
import { CHECKOUT_STEPS } from './constants';

const DischargeStepper = ({ step, maxReachable, onStepClick, isDischarged, hasGatePass }) => (
  <div className="flex flex-wrap items-center gap-2 text-xs border-b pb-3">
    {CHECKOUT_STEPS.map((s, i) => {
      const done = s.id < step || (hasGatePass && s.id <= 4);
      const active = s.id === step;
      const skipped = isDischarged && s.id === 3 && step === 4;
      const clickable = onStepClick && s.id <= maxReachable && !skipped;
      return (
        <React.Fragment key={s.key}>
          <button
            type="button"
            disabled={!clickable}
            onClick={() => clickable && onStepClick(s.id)}
            className={
              'flex items-center gap-1.5 rounded-full px-2 py-1 transition ' +
              (active ? 'bg-blue-600 text-white' :
                done ? 'bg-green-100 text-green-800' :
                  skipped ? 'bg-gray-100 text-gray-400 line-through' :
                    'bg-gray-100 text-gray-600') +
              (clickable && !active ? ' hover:ring-1 hover:ring-blue-300 cursor-pointer' : '')
            }
          >
            <span className={
              'h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-semibold ' +
              (active ? 'bg-white/20' : done ? 'bg-green-600 text-white' : 'bg-gray-300 text-gray-700')
            }>
              {done && !active ? '✓' : s.id}
            </span>
            <span className={active ? 'font-semibold' : ''}>{s.label}</span>
          </button>
          {i < CHECKOUT_STEPS.length - 1 && <span className="text-gray-300 hidden sm:inline">›</span>}
        </React.Fragment>
      );
    })}
  </div>
);

export default DischargeStepper;
