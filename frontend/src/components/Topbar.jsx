import React from 'react';
import { Search, Plus, Bell, Zap, User } from 'lucide-react';

export default function Topbar() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/70 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="relative">
            <input placeholder="Search companies, leads, quotations..." className="w-72 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm placeholder:text-slate-400" />
            <Search className="absolute right-3 top-2.5 h-4 w-4 text-slate-400" />
          </div>
          <button className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-2 text-sm text-white hover:bg-slate-800">
            <Plus className="h-4 w-4" /> Quick Add
          </button>
        </div>

        <div className="flex items-center gap-3">
          <button className="rounded-full p-2 hover:bg-slate-50"><Bell className="h-5 w-5 text-slate-600" /></button>
          <button className="rounded-full p-2 hover:bg-slate-50"><Zap className="h-5 w-5 text-slate-600" /></button>
          <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-sm">
            <User className="h-4 w-4 text-slate-600" />
            <span className="hidden sm:inline">User</span>
          </div>
        </div>
      </div>
    </header>
  );
}
