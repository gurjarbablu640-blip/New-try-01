/**
 * Dashboard - Main App View
 * ==========================================
 * Full AI Sales Intelligence Dashboard
 */

import React, { useState } from 'react';

import BuyingWindowBoard from './BuyingWindowBoard';

import TaskList from './TaskList';

import LookalikeFeed from './LookalikeFeed';

import PipelineBoard from './PipelineBoard';

import SmartSearch from './SmartSearch';

import ABInsights from './ABInsights';

import ICPInsights from './ICPInsights';

import ActivityPanel from "./ActivityPanel";

import TodayFollowups from "./TodayFollowups";

import OrdersPanel from "./OrdersPanel";

import LeadDashboard from './LeadDashboard';


export default function Dashboard() {

  const [selectedCompany, setSelectedCompany] = useState(null);

  const handleCompanyClick = (companyId) => {
    setSelectedCompany(companyId);
    console.log('Open company:', companyId);
  };

  const stats = [
    { label: 'Qualified Leads', value: '148', change: '+18%', tone: 'blue' },
    { label: 'Pipeline Value', value: '₹18.4L', change: '+12%', tone: 'green' },
    { label: 'Follow-ups Today', value: '24', change: '8 due now', tone: 'orange' },
    { label: 'Win Rate', value: '31%', change: '+4.2%', tone: 'purple' },
  ];

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800">
      <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-600 to-violet-600 text-lg font-bold text-white shadow-lg shadow-blue-500/25">
              S
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">Salesoorja AI</h1>
              <p className="text-sm text-slate-500">AI Sales Intelligence Platform</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-700">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
              System Active
            </div>
            <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-600">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 p-6">
        <section className="rounded-3xl border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-blue-50 p-6 shadow-sm">
          <div className="mb-5 flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">Executive Overview</p>
              <h2 className="mt-2 text-3xl font-bold text-slate-900">Revenue operations dashboard</h2>
            </div>
            <button className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-slate-900/10 transition hover:bg-slate-800">
              + New campaign
            </button>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {stats.map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-500">{item.label}</span>
                  <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    item.tone === 'blue' ? 'bg-blue-100 text-blue-700' :
                    item.tone === 'green' ? 'bg-emerald-100 text-emerald-700' :
                    item.tone === 'orange' ? 'bg-amber-100 text-amber-700' :
                    'bg-violet-100 text-violet-700'
                  }`}>{item.change}</span>
                </div>
                <div className="mt-4 text-3xl font-bold text-slate-900">{item.value}</div>
              </div>
            ))}
          </div>
        </section>

        <SmartSearch onCompanyClick={handleCompanyClick} />

        <LeadDashboard />

        <BuyingWindowBoard onCompanyClick={handleCompanyClick} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <TaskList onCompanyClick={handleCompanyClick} />
          </div>
          <div>
            <LookalikeFeed onCompanyClick={handleCompanyClick} />
          </div>
        </div>

        <PipelineBoard onCompanyClick={handleCompanyClick} />

        <TodayFollowups />

        <ActivityPanel />

        <OrdersPanel />

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <ABInsights />
          <ICPInsights />
        </div>
      </main>
    </div>
  );
}