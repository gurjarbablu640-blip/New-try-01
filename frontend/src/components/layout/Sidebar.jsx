import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Building2,
  GitPullRequest,
  Send,
  Inbox,
  FileText,
  Gauge,
  ShieldAlert,
  MapPin,
  BarChart3,
  Bot,
  Settings,
  ChevronLeft,
  ChevronRight,
  Flame,
  Zap,
} from "lucide-react";

export default function Sidebar({ collapsed, setCollapsed }) {
  const location = useLocation();

  const navItems = [
    { to: "/dashboard", label: "Command Center", icon: LayoutDashboard },
    { to: "/intelligence", label: "Decision Intel", icon: Zap, badge: "Core", highlight: true },
    { to: "/leads", label: "Lead Factory", icon: Users, badge: "AI" },
    { to: "/companies", label: "Companies 360", icon: Building2 },
    { to: "/pipeline", label: "Pipeline CRM", icon: GitPullRequest },
    { to: "/campaigns", label: "Campaigns", icon: Send },
    { to: "/inbox", label: "Sales Inbox", icon: Inbox, badge: "Live" },
    { to: "/quotations", label: "Quotations", icon: FileText },
    { to: "/calibration", label: "Calibration Intel", icon: Gauge, badge: "NABL" },
    { to: "/competitors", label: "Competitors", icon: ShieldAlert },
    { to: "/territory", label: "Territory / Trips", icon: MapPin },
    { to: "/analytics", label: "Sales Analytics", icon: BarChart3 },
    { to: "/assistant", label: "Ask Oorja AI", icon: Bot },
    { to: "/settings", label: "Settings", icon: Settings },
  ];

  return (
    <aside
      className={`fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-dark-border bg-[#0D131F] transition-all duration-300 ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between border-b border-dark-border px-4">
        {!collapsed ? (
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-primary to-brand-cyan text-white shadow-md shadow-brand-primary/20">
              <Flame className="h-5 w-5" />
            </div>
            <div>
              <span className="font-bold tracking-tight text-white">Oorja Sales OS</span>
              <span className="block text-[10px] font-medium tracking-wider text-brand-cyan">AI METROLOGY COCKPIT</span>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-primary to-brand-cyan text-white shadow-md">
            <Flame className="h-5 w-5" />
          </div>
        )}

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="rounded-lg p-1.5 text-dark-muted hover:bg-dark-hover hover:text-white"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>

      {/* Navigation Items */}
      <nav className="flex-1 space-y-1.5 overflow-y-auto px-3 py-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.to || (item.to !== "/dashboard" && location.pathname.startsWith(item.to));

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? "bg-brand-primary/15 text-brand-primary border border-brand-primary/30 shadow-sm"
                  : item.highlight
                  ? "bg-brand-cyan/10 text-brand-cyan hover:bg-brand-cyan/20 border border-brand-cyan/20"
                  : "text-dark-muted hover:bg-dark-panel hover:text-white"
              } ${collapsed ? "justify-center px-2" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <Icon
                className={`h-5 w-5 flex-shrink-0 transition-transform group-hover:scale-105 ${
                  isActive ? "text-brand-primary" : item.highlight ? "text-brand-cyan" : "text-dark-muted group-hover:text-white"
                }`}
              />

              {!collapsed && (
                <div className="flex flex-1 items-center justify-between">
                  <span className="truncate">{item.label}</span>
                  {item.badge && (
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                        item.badge === "Live"
                          ? "bg-brand-emerald/20 text-brand-emerald border border-brand-emerald/30"
                          : item.badge === "NABL"
                          ? "bg-brand-cyan/20 text-brand-cyan border border-brand-cyan/30"
                          : "bg-brand-secondary/20 text-brand-secondary border border-brand-secondary/30"
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </div>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Sidebar Footer */}
      <div className="border-t border-dark-border p-3">
        {!collapsed ? (
          <div className="flex items-center justify-between rounded-lg bg-dark-card p-2.5">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
              </span>
              <div className="text-xs">
                <div className="font-semibold text-white">System Active</div>
                <div className="text-[10px] text-dark-muted">Test Mode Protected</div>
              </div>
            </div>
            <span className="rounded bg-brand-primary/10 px-1.5 py-0.5 text-[10px] font-mono text-brand-primary">
              v1.0
            </span>
          </div>
        ) : (
          <div className="flex justify-center py-1">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
