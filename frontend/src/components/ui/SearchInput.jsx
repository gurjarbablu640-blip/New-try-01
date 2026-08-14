import React from 'react';
import { Search } from 'lucide-react';

export default function SearchInput({ className = '', ...props }) {
  return (
    <div className={`relative ${className}`}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        type="search"
        className="h-10 w-full rounded-xl border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-800 placeholder:text-slate-400 transition-all duration-200 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
        {...props}
      />
    </div>
  );
}
