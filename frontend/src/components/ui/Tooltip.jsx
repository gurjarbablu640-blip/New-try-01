import React from 'react';

export default function Tooltip({ children, text }) {
  return (
    <div className="group relative inline-flex">
      {children}
      <span className="pointer-events-none absolute -top-10 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded-lg bg-slate-900 px-2 py-1 text-[10px] font-medium text-white shadow-lg group-hover:inline-block">
        {text}
      </span>
    </div>
  );
}
