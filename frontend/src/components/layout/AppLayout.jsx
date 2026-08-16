import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import CompanyDrawer from "../common/CompanyDrawer";

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState(null);

  const handleOpenCompany = (companyId) => {
    setSelectedCompanyId(companyId);
  };

  const handleCloseCompany = () => {
    setSelectedCompanyId(null);
  };

  return (
    <div className="min-h-screen bg-[#0A0E17] text-white">
      {/* Sidebar */}
      <Sidebar collapsed={collapsed} setCollapsed={setCollapsed} />

      {/* Main Content Area */}
      <div className={`flex min-h-screen flex-col transition-all duration-300 ${collapsed ? "pl-20" : "pl-64"}`}>
        <TopBar onOpenCompany={handleOpenCompany} collapsed={collapsed} />

        <main className="flex-1 p-6 md:p-8">
          <div className="mx-auto max-w-7xl">
            {/* Child route outlet with company opener callback */}
            <Outlet context={{ onOpenCompany: handleOpenCompany }} />
          </div>
        </main>
      </div>

      {/* Global Contextual Company Drawer */}
      {selectedCompanyId && (
        <CompanyDrawer companyId={selectedCompanyId} onClose={handleCloseCompany} />
      )}
    </div>
  );
}
