import React from 'react';

export default function Tabs({ tabs = [], value, onChange, className = '' }) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {tabs.map((tab) => {
        const active = value === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange?.(tab.value)}
            className={`rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
              active ? 'bg-violet-50 text-violet-700 ring-1 ring-violet-200' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
