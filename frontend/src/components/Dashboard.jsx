/**
 * Dashboard - Main App View
 * ==========================================
 * Oorja Sales OS Dashboard
 */

import React, { useState } from 'react';

import BuyingWindowBoard from './BuyingWindowBoard';
import TaskList from './TaskList';
import LookalikeFeed from './LookalikeFeed';
import PipelineBoard from './PipelineBoard';
import SmartSearch from './SmartSearch';
import ABInsights from './ABInsights';
import ICPInsights from './ICPInsights';
import ActivityPanel from './ActivityPanel';
import TodayFollowups from './TodayFollowups';
import OrdersPanel from './OrdersPanel';
import LeadDashboard from './LeadDashboard';
import SalesOSCommandCenter from './SalesOSCommandCenter';
import QuotationIntelligence from './QuotationIntelligence';
import AskOorjaAI from './AskOorjaAI';
import CampaignEngine from './CampaignEngine';
import CompetitorIntelligence from './CompetitorIntelligence';
import LearningAnalytics from './LearningAnalytics';
import Company360 from './Company360';

export default function Dashboard() {
  const [selectedCompany, setSelectedCompany] = useState(null);

  const handleCompanyClick = (companyId) => {
    setSelectedCompany(companyId);
    console.log('Open company:', companyId);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white border-b px-6 py-4 sticky top-0 z-50">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Oorja Sales OS</h1>
            <p className="text-sm text-gray-500">AI Sales Intelligence Platform</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="bg-green-100 text-green-700 px-3 py-1 rounded-full text-sm font-medium">System Active</div>
            <span className="text-sm text-gray-600">
              {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'short' })}
            </span>
          </div>
        </div>
      </header>

      <main className="p-6 space-y-6 max-w-7xl mx-auto">
        <AskOorjaAI />
        <SalesOSCommandCenter />
        <LearningAnalytics />
        <Company360 />
        <SmartSearch onCompanyClick={handleCompanyClick} />
        <LeadDashboard />
        <QuotationIntelligence />
        <CampaignEngine />
        <CompetitorIntelligence />
        <BuyingWindowBoard onCompanyClick={handleCompanyClick} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ABInsights />
          <ICPInsights />
        </div>

        {selectedCompany && (
          <div className="fixed bottom-4 right-4 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg">
            Company selected: #{selectedCompany}
          </div>
        )}
      </main>
    </div>
  );
}
