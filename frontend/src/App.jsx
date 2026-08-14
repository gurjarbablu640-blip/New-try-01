/**
 * Salesoorja AI - Main App Entry Point
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppShell from './layouts/AppShell';
import DashboardHome from './pages/DashboardHome';
import LeadsPage from './pages/LeadsPage';
import CompaniesPage from './pages/CompaniesPage';
import Company360Page from './pages/Company360Page';
import PipelinePage from './pages/PipelinePage';
import QuotationsPage from './pages/QuotationsPage';
import CampaignsPage from './pages/CampaignsPage';
import ResearchPage from './pages/ResearchPage';
import AnalyticsPage from './pages/AnalyticsPage';
import AskPage from './pages/AskPage';
import SettingsPage from './pages/SettingsPage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardHome />} />
          <Route path="leads" element={<LeadsPage />} />
          <Route path="companies" element={<CompaniesPage />} />
          <Route path="companies/:id" element={<Company360Page />} />
          <Route path="companies/:id/360" element={<Company360Page />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="pipeline/by-location" element={<PipelinePage />} />
          <Route path="pipeline/by-stage" element={<PipelinePage />} />
          <Route path="pipeline/all" element={<PipelinePage />} />
          <Route path="pipeline/tasks" element={<PipelinePage />} />
          <Route path="quotations" element={<QuotationsPage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="research" element={<ResearchPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
