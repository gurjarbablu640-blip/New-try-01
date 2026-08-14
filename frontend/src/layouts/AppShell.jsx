import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Topbar from '../components/Topbar';

export default function AppShell() {
  return (
    <div className="min-h-screen flex bg-slate-100 text-slate-800">
      <Sidebar />
      <div className="flex w-full flex-1 flex-col">
        <Topbar />
        <main className="mx-auto w-full max-w-7xl p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
