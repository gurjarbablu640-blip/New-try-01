import React from 'react';

const base = 'inline-flex items-center justify-center gap-2 rounded-xl border text-sm font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-violet-500/30 disabled:cursor-not-allowed disabled:opacity-50';

const variants = {
  primary: 'border-violet-600 bg-violet-600 text-white shadow-sm hover:bg-violet-500',
  secondary: 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
  ghost: 'border-transparent bg-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  success: 'border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500',
  danger: 'border-red-600 bg-red-600 text-white hover:bg-red-500',
  purple: 'border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100',
};

const sizes = {
  sm: 'h-9 px-3 py-2 text-xs',
  md: 'h-10 px-4 py-2.5 text-sm',
  lg: 'h-11 px-5 py-3 text-sm',
};

export default function Button({ children, className = '', variant = 'secondary', size = 'md', ...props }) {
  return (
    <button className={`${base} ${variants[variant] || variants.secondary} ${sizes[size] || sizes.md} ${className}`} {...props}>
      {children}
    </button>
  );
}
