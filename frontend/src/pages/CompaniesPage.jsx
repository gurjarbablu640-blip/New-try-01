import React from 'react';
import SmartSearch from '../components/SmartSearch';

export default function CompaniesPage() {
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Companies</h1>
      <p className="mb-3 text-sm text-slate-500">Search and browse companies in CRM</p>
      <SmartSearch />
    </div>
  );
}
