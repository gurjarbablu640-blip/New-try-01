import React from 'react';

export default function Skeleton({ className = '', lines = 1 }) {
  return (
    <div className={`animate-pulse ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="mb-2 h-4 rounded bg-slate-200" />
      ))}
    </div>
  );
}
