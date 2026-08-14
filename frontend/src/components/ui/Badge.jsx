import React from 'react';

const tones = {
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  cyan: 'bg-cyan-50 text-cyan-700 ring-cyan-200',
  emerald: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-amber-200',
  red: 'bg-red-50 text-red-700 ring-red-200',
};

export default function Badge({ children, tone = 'slate', className = '' }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold ring-1 ring-inset ${tones[tone] || tones.slate} ${className}`}>
      {children}
    </span>
  );
}
