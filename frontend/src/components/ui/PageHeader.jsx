import React from 'react';

export default function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="mb-4 flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
