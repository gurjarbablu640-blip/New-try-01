/**
 * Dashboard - Main App View
 * ===========================
 * Order of widgets (as specified):
 *   1. BuyingWindowBoard (primary widget - top of page)
 *   2. TaskList for today
 *   3. LookalikeFeed
 *   4. Then existing stats/charts below
 *
 * Also includes SmartSearch at the very top.
 */
import React, { useState } from 'react';
import BuyingWindowBoard from './BuyingWindowBoard';
import TaskList from './TaskList';
import LookalikeFeed from './LookalikeFeed';
import PipelineBoard from './PipelineBoard';
import SmartSearch from './SmartSearch';
import ABInsights from './ABInsights';
import ICPInsights from './ICPInsights';

export default function Dashboard() {
  const [selectedCompany, setSelectedCompany] = useState(null);

  const handleCompanyClick = (companyId) => {
    setSelectedCompany(companyId);
    // In full app, this would open CompanyDrawer
    console.log('Open company:', companyId);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              Salesoorja AI
            </h1>
            <p className="text-sm text-gray-500">
              Sales Intelligence Dashboard
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">
              {new Date().toLocaleDateString('en-IN', {
                weekday: 'long',
                day: 'numeric',
                month: 'short',
              })}
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Smart Search - Top */}
        <SmartSearch onCompanyClick={handleCompanyClick} />

        {/* 1. Buying Window Board - PRIMARY WIDGET */}
        <BuyingWindowBoard onCompanyClick={handleCompanyClick} />

        {/* 2. Task List + 3. Lookalike Feed - Side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <TaskList onCompanyClick={handleCompanyClick} />
          </div>
          <div>
            <LookalikeFeed onCompanyClick={handleCompanyClick} />
          </div>
        </div>

        {/* Pipeline Board */}
        <PipelineBoard onCompanyClick={handleCompanyClick} />

        {/* Analytics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ABInsights />
          <ICPInsights />
        </div>
      </main>
    </div>
  );
}
