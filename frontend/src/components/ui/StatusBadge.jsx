import React from 'react';

export default function StatusBadge({ status }){
  const map = {
    Open: 'bg-emerald-50 text-emerald-700',
    Draft: 'bg-slate-100 text-slate-700',
    Approved: 'bg-emerald-50 text-emerald-700',
    Pending: 'bg-amber-50 text-amber-700',
    Lost: 'bg-red-50 text-red-700'
  };
  const cls = map[status] || 'bg-slate-100 text-slate-700';
  return <span className={`inline-block rounded-full px-2 py-1 text-xs font-semibold ${cls}`}>{status || 'Unknown'}</span>;
}
