import React from 'react';
import TodayFollowups from '../components/TodayFollowups';
import PipelineBoard from '../components/PipelineBoard';
import TaskList from '../components/TaskList';
import ActivityPanel from '../components/ActivityPanel';
import SalesOSCommandCenter from '../components/SalesOSCommandCenter';

export default function DashboardHome() {
  return (
    <div className="space-y-6">
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Command Center</h1>
            <p className="text-sm text-slate-500">Today's priorities and recommended actions</p>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border bg-white p-4">{/* KPI card placeholders */}
            <div className="text-xs text-slate-500">Follow-ups due</div>
            <div className="mt-2 text-2xl font-semibold">24</div>
          </div>
          <div className="rounded-xl border bg-white p-4">
            <div className="text-xs text-slate-500">Pipeline value</div>
            <div className="mt-2 text-2xl font-semibold">₹18.4L</div>
          </div>
          <div className="rounded-xl border bg-white p-4">
            <div className="text-xs text-slate-500">Top opportunities</div>
            <div className="mt-2 text-2xl font-semibold">3</div>
          </div>
          <div className="rounded-xl border bg-white p-4">
            <div className="text-xs text-slate-500">AI recommended</div>
            <div className="mt-2 text-2xl font-semibold">5 actions</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <h3 className="mb-3 text-lg font-semibold">Pipeline Snapshot</h3>
            <PipelineBoard compact />
          </div>

          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <h3 className="mb-3 text-lg font-semibold">Top Tasks / Priorities</h3>
            <TaskList compact />
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <h3 className="text-lg font-semibold">Follow-ups Due</h3>
            <TodayFollowups compact />
          </div>

          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <h3 className="text-lg font-semibold">AI Recommended Actions</h3>
            <SalesOSCommandCenter compact />
          </div>

          <div className="rounded-2xl bg-white p-4 shadow-sm">
            <h3 className="text-lg font-semibold">Recent Activity</h3>
            <ActivityPanel compact />
          </div>
        </div>
      </div>
    </div>
  );
}
