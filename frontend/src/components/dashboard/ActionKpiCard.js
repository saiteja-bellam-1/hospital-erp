import React from 'react';
import { Card, CardContent } from '../ui/card';
import { cn } from '../../lib/utils';

/**
 * Gradient KPI tile matching Hospital Overview / system dashboard style.
 * Optional onClick makes the card a drill-down affordance.
 */
export default function ActionKpiCard({
  icon: Icon,
  label,
  value,
  sub,
  tone = 'slate',
  onClick,
  className,
}) {
  const tones = {
    slate: {
      card: 'from-slate-50 to-white',
      label: 'text-slate-600',
      iconBg: 'bg-slate-100',
      icon: 'text-slate-600',
    },
    green: {
      card: 'from-emerald-50 to-white',
      label: 'text-emerald-600',
      iconBg: 'bg-emerald-100',
      icon: 'text-emerald-600',
    },
    blue: {
      card: 'from-blue-50 to-white',
      label: 'text-blue-600',
      iconBg: 'bg-blue-100',
      icon: 'text-blue-600',
    },
    amber: {
      card: 'from-amber-50 to-white',
      label: 'text-amber-600',
      iconBg: 'bg-amber-100',
      icon: 'text-amber-600',
    },
    orange: {
      card: 'from-orange-50 to-white',
      label: 'text-orange-600',
      iconBg: 'bg-orange-100',
      icon: 'text-orange-600',
    },
    red: {
      card: 'from-rose-50 to-white',
      label: 'text-rose-600',
      iconBg: 'bg-rose-100',
      icon: 'text-rose-600',
    },
    purple: {
      card: 'from-purple-50 to-white',
      label: 'text-purple-600',
      iconBg: 'bg-purple-100',
      icon: 'text-purple-600',
    },
    cyan: {
      card: 'from-cyan-50 to-white',
      label: 'text-cyan-600',
      iconBg: 'bg-cyan-100',
      icon: 'text-cyan-600',
    },
  };
  const t = tones[tone] || tones.slate;
  const clickable = typeof onClick === 'function';

  return (
    <Card
      className={cn(
        'border-0 shadow-sm bg-gradient-to-br',
        t.card,
        clickable && 'cursor-pointer transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-offset-1 focus-within:ring-blue-400',
        className,
      )}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? onClick : undefined}
      onKeyDown={clickable ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(e);
        }
      } : undefined}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cn('text-xs font-medium uppercase tracking-wide', t.label)}>{label}</p>
            <p className="text-3xl font-bold text-gray-900 mt-1 truncate">{value}</p>
            {sub && <p className="text-xs text-gray-500 mt-1.5">{sub}</p>}
          </div>
          {Icon && (
            <div className={cn('h-10 w-10 rounded-xl flex items-center justify-center shrink-0', t.iconBg)}>
              <Icon className={cn('h-5 w-5', t.icon)} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
