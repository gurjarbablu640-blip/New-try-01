import React from 'react';

export default function Input({ className = '', ...props }) {
  return (
    <input
      className={`h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 placeholder:text-slate-400 transition-all duration-200 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100 ${className}`}
      {...props}
    />
  );
}
