import React from 'react';
export default function EmptyState({ title, description, icon: Icon, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-slate-200 bg-white p-8 text-center">
      {Icon && <Icon className="h-8 w-8 text-slate-400" />}
      <div className="text-lg font-semibold text-slate-800">{title}</div>
      {description && <div className="text-sm text-slate-500">{description}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
