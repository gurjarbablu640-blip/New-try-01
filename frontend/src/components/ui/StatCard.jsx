import React from 'react';

export default function StatCard({ label, value, hint, tone = 'indigo' }) {
  const toneBg = {
    indigo: 'bg-indigo-50 text-indigo-700',
    green: 'bg-emerald-50 text-emerald-700',
    amber: 'bg-amber-50 text-amber-700',
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 flex items-baseline justify-between">
        <div className="text-2xl font-semibold text-slate-900">{value}</div>
        {hint && <div className={`rounded-full px-2 py-1 text-xs font-medium ${toneBg[tone] || toneBg.indigo}`}>{hint}</div>}
      </div>
    </div>
  );
}
