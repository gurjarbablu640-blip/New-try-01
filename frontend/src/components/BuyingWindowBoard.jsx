/**
 * Module 16: Buying Window Board
 * ================================
 * The most powerful view in the app.
 * 3 columns: "Next 30 days" | "Next 60 days" | "Next 90 days"
 * This is the FIRST thing a salesperson sees every morning.
 */
import React, { useState, useEffect } from 'react';
import { getBuyingWindow } from '../api';

const WINDOW_CONFIG = {
  next_30_days: { label: 'Next 30 Days', color: 'red', emoji: '🔥' },
  next_60_days: { label: 'Next 60 Days', color: 'orange', emoji: '⚡' },
  next_90_days: { label: 'Next 90 Days', color: 'blue', emoji: '📊' },
};

const TIER_COLORS = {
  'High-Value Recurring': 'bg-green-100 text-green-800 border-green-300',
  'Compliance-Driven': 'bg-blue-100 text-blue-800 border-blue-300',
  'Growth Potential': 'bg-purple-100 text-purple-800 border-purple-300',
  'Low Potential': 'bg-gray-100 text-gray-800 border-gray-300',
};

export default function BuyingWindowBoard({ onCompanyClick }) {
  const [board, setBoard] = useState({});
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const res = await getBuyingWindow();
      setBoard(res.data.board || {});
      setSummary(res.data.summary || {});
    } catch (err) {
      console.error('Failed to load buying window:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="animate-pulse p-4">Loading buying window...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900">
          Predicted Buying Window
        </h2>
        <span className="text-sm text-gray-500">
          {summary.total_hot_leads || 0} hot leads
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {Object.entries(WINDOW_CONFIG).map(([key, config]) => (
          <div key={key} className="border rounded-lg p-3">
            <div className="flex items-center gap-2 mb-3">
              <span>{config.emoji}</span>
              <h3 className="font-semibold text-sm">{config.label}</h3>
              <span className="ml-auto bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded-full">
                {(board[key] || []).length}
              </span>
            </div>

            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {(board[key] || []).map((company) => (
                <CompanyCard
                  key={company.company_id}
                  company={company}
                  onClick={() => onCompanyClick?.(company.company_id)}
                />
              ))}
              {(board[key] || []).length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">
                  No companies in this window
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CompanyCard({ company, onClick }) {
  const tierClass = TIER_COLORS[company.tier] || TIER_COLORS['Low Potential'];

  return (
    <div
      onClick={onClick}
      className="border rounded-md p-2 cursor-pointer hover:shadow-md transition-shadow bg-white"
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-sm text-gray-900 truncate">
            {company.name}
          </p>
          <p className="text-xs text-gray-500">{company.city}, {company.state}</p>
        </div>
        <span className="text-xs font-bold text-gray-700 ml-2">
          {company.icp_score}
        </span>
      </div>

      <div className="mt-1 flex items-center gap-1 flex-wrap">
        <span className={`text-xs px-1.5 py-0.5 rounded border ${tierClass}`}>
          {company.tier}
        </span>
        {company.top_signal && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">
            {company.top_signal.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      {company.signal_reason && (
        <p className="text-xs text-gray-500 mt-1 truncate">
          {company.signal_reason}
        </p>
      )}

      <div className="mt-1 flex items-center justify-between">
        <span className="text-xs text-gray-400">{company.pipeline_stage}</span>
        {company.pipeline_stage === 'Not in pipeline' && (
          <button className="text-xs text-blue-600 hover:underline">
            Start outreach
          </button>
        )}
      </div>
    </div>
  );
}
