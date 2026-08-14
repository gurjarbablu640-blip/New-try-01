import React from 'react';

export default function IconButton({ icon: Icon, label, className = '', variant = 'secondary', ...props }) {
  const variants = {
    primary: 'bg-violet-600 text-white hover:bg-violet-500',
    secondary: 'bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900',
    ghost: 'bg-transparent text-slate-500 hover:bg-slate-100 hover:text-slate-900',
    success: 'bg-emerald-600 text-white hover:bg-emerald-500',
    danger: 'bg-red-600 text-white hover:bg-red-500',
  };

  return (
    <button
      type="button"
      aria-label={label}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-violet-500/30 disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant] || variants.secondary} ${className}`}
      {...props}
    >
      {Icon && <Icon className="h-4 w-4" />}
    </button>
  );
}
