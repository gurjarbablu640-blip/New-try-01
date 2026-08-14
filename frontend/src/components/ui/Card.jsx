import React from 'react';

export default function Card({ children, className = '', padded = true, as: Component = 'div', ...props }) {
  return (
    <Component
      className={`rounded-2xl border border-slate-200 bg-white shadow-sm shadow-slate-200/60 ${padded ? 'p-4' : ''} ${className}`}
      {...props}
    >
      {children}
    </Component>
  );
}
