import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Building2,
  GitBranch,
  FileText,
  Send,
  Search,
  BarChart3,
  Sparkles,
  Settings,
} from 'lucide-react';

const items = [
  { to: '/dashboard', label: 'Home', icon: LayoutDashboard },
  { to: '/leads', label: 'Leads', icon: Users },
  { to: '/companies', label: 'Companies', icon: Building2 },
  { to: '/pipeline', label: 'Pipeline', icon: GitBranch, submenu: [
    { to: '/pipeline', label: 'Overview' },
    { to: '/pipeline/by-location', label: 'By Location' },
    { to: '/pipeline/by-stage', label: 'By Stage' },
    { to: '/pipeline/all', label: 'All Opportunities' },
    { to: '/pipeline/tasks', label: 'Tasks' },
  ] },
  { to: '/quotations', label: 'Quotations', icon: FileText },
  { to: '/campaigns', label: 'Campaigns', icon: Send },
  { to: '/research', label: 'Research', icon: Search },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/ask', label: 'Ask Oorja', icon: Sparkles },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside className={`h-screen ${collapsed ? 'w-16' : 'w-64'} bg-white border-r border-slate-200 transition-all`}> 
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3 p-4">
          <div className={`flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600 text-white font-bold ${collapsed ? 'mx-auto' : ''}`}>O</div>
          {!collapsed && (
            <div>
              <div className="text-lg font-semibold">Oorja</div>
              <div className="text-xs text-slate-500">Sales OS</div>
            </div>
          )}
        </div>

        <nav className="flex-1 px-1">
          {items.map((it) => {
            const Icon = it.icon;
            return (
              <div key={it.to}>
              <NavLink
                to={it.to}
                className={({ isActive }) =>
                  `group flex items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-slate-50 ${isActive ? 'bg-slate-100 font-medium' : 'text-slate-700'}`
                }
                title={it.label}
              >
                <Icon className="h-5 w-5 text-slate-600 group-hover:text-slate-900" />
                {!collapsed && <span>{it.label}</span>}
              </NavLink>

              {!collapsed && it.submenu && (
                <div className="ml-8 mt-1 flex flex-col text-sm text-slate-500">
                  {it.submenu.map((s) => (
                    <NavLink key={s.to} to={s.to} className="rounded-md px-2 py-1 hover:bg-slate-50">{s.label}</NavLink>
                  ))}
                </div>
              )}
            </div>
            );
          })}
        </nav>

        <div className="p-3">
          <button
            onClick={() => setCollapsed((c) => !c)}
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50"
          >
            {collapsed ? 'Expand' : 'Collapse'}
          </button>
        </div>
      </div>
    </aside>
  );
}
