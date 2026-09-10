import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";

// Lead Generation Workspace Pages
import DashboardPage from "./pages/DashboardPage";
import IntelligencePage from "./pages/IntelligencePage";
import LeadFactoryPage from "./pages/LeadFactoryPage";
import CompaniesPage from "./pages/CompaniesPage";
import PipelinePage from "./pages/PipelinePage";
import CampaignsPage from "./pages/CampaignsPage";
import InboxPage from "./pages/InboxPage";
import CalibrationPage from "./pages/CalibrationPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="intelligence" element={<IntelligencePage />} />
          <Route path="leads" element={<LeadFactoryPage />} />
          <Route path="companies" element={<CompaniesPage />} />
          <Route path="pipeline" element={<PipelinePage />} />
          <Route path="campaigns" element={<CampaignsPage />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="calibration" element={<CalibrationPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
