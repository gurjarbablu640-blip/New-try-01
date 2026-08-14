import React from 'react';

export default function Select({ className = '', children, ...props }) {
  return (
    <select
      className={`h-10 appearance-none rounded-xl border border-slate-200 bg-white px-3 pr-8 text-sm text-slate-800 transition-all duration-200 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 ${className}`}
      {...props}
    >
      {children}
    </select>
  );
}
