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

    console.log(
      'Open company:',
      companyId
    );
  };

  return (

    <div className="min-h-screen bg-gray-100">

      {/* ===================================================== */}
      {/* HEADER */}
      {/* ===================================================== */}

      <header
        className="
          bg-white
          border-b
          px-6
          py-4
          sticky
          top-0
          z-50
        "
      >

        <div
          className="
            flex
            items-center
            justify-between
          "
        >

          {/* LEFT */}
          <div>

            <h1
              className="
                text-2xl
                font-bold
                text-gray-900
              "
            >
              Salesoorja AI
            </h1>

            <p
              className="
                text-sm
                text-gray-500
              "
            >
              AI Sales Intelligence Platform
            </p>

          </div>

          {/* RIGHT */}
          <div
            className="
              flex
              items-center
              gap-3
            "
          >

            <div
              className="
                bg-green-100
                text-green-700
                px-3
                py-1
                rounded-full
                text-sm
                font-medium
              "
            >
              System Active
            </div>

            <span
              className="
                text-sm
                text-gray-600
              "
            >
              {new Date().toLocaleDateString(
                'en-IN',
                {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'short',
                }
              )}
            </span>

          </div>

        </div>

      </header>

      {/* ===================================================== */}
      {/* MAIN CONTENT */}
      {/* ===================================================== */}

      <main
        className="
          p-6
          space-y-6
          max-w-7xl
          mx-auto
        "
      >

        {/* ================================================= */}
        {/* SMART SEARCH */}
        {/* ================================================= */}

        <SmartSearch
          onCompanyClick={
            handleCompanyClick
          }
        />

        {/* ================================================= */}
        {/* LIVE LEADS DASHBOARD */}
        {/* ================================================= */}

        <LeadDashboard />

        {/* ================================================= */}
        {/* BUYING WINDOW BOARD */}
        {/* ================================================= */}

        <BuyingWindowBoard
          onCompanyClick={
            handleCompanyClick
          }
        />

        {/* ================================================= */}
        {/* TASKS + LOOKALIKES */}
        {/* ================================================= */}

        <div
          className="
            grid
            grid-cols-1
            lg:grid-cols-3
            gap-6
          "
        >

          {/* TASKS */}
          <div className="lg:col-span-2">

            <TaskList
              onCompanyClick={
                handleCompanyClick
              }
            />

          </div>

          {/* LOOKALIKES */}
          <div>

            <LookalikeFeed
              onCompanyClick={
                handleCompanyClick
              }
            />

          </div>

        </div>

        {/* ================================================= */}
        {/* PIPELINE */}
        {/* ================================================= */}

        <PipelineBoard
          onCompanyClick={
            handleCompanyClick
          }
        />

        {/* ================================================= */}
        {/* TODAY FOLLOWUPS */}
        {/* ================================================= */}

        <TodayFollowups />

        {/* ================================================= */}
        {/* ACTIVITY PANEL */}
        {/* ================================================= */}

        <ActivityPanel />

        {/* ================================================= */}
        {/* ORDERS PANEL */}
        {/* ================================================= */}

        <OrdersPanel />

        {/* ================================================= */}
        {/* ANALYTICS */}
        {/* ================================================= */}

        <div
          className="
            grid
            grid-cols-1
            md:grid-cols-2
            gap-6
          "
        >

          <ABInsights />

          <ICPInsights />

        </div>

      </main>

    </div>
  );
}