import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";

// Workspace Pages
import DashboardPage from "./pages/DashboardPage";
import LeadFactoryPage from "./pages/LeadFactoryPage";
import CompaniesPage from "./pages/CompaniesPage";
import PipelinePage from "./pages/PipelinePage";
import CampaignsPage from "./pages/CampaignsPage";
import InboxPage from "./pages/InboxPage";
import QuotationsPage from "./pages/QuotationsPage";
import CalibrationPage from "./pages/CalibrationPage";
import CompetitorsPage from "./pages/CompetitorsPage";
import TerritoryPage from "./pages/TerritoryPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import AssistantPage from "./pages/AssistantPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="leads" element={<LeadFactoryPage />} />
          <Route path="companies" element={<CompaniesPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="quotations" element={<QuotationsPage />} />
          <Route path="calibration" element={<CalibrationPage />} />
          <Route path="competitors" element={<CompetitorsPage />} />
          <Route path="territory" element={<TerritoryPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="assistant" element={<AssistantPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
