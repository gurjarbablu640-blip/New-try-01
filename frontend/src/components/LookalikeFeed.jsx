/**
 * LookalikeFeed Component
 * =========================
 * Shows new lookalike leads found by AI.
 * Badge: "17 new lookalike leads found today"
 */
import React, { useState, useEffect } from 'react';
import { getLookalikes, approveLookalikes } from '../api';

export default function LookalikeFeed({ onCompanyClick }) {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState([]);

  useEffect(() => {
    loadLeads();
  }, []);

  const loadLeads = async () => {
    try {
      const res = await getLookalikes();
      setLeads(res.data.leads || []);
    } catch (err) {
      console.error('Failed to load lookalikes:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (selected.length === 0) return;
    try {
      await approveLookalikes(selected);
      setLeads(leads.filter(l => !selected.includes(l.company_id)));
      setSelected([]);
    } catch (err) {
      console.error('Approve error:', err);
    }
  };

  const toggleSelect = (id) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  if (loading) return <div className="animate-pulse p-4">Loading...</div>;

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-bold text-gray-900">
          AI Lookalike Leads
        </h2>
        {leads.length > 0 && (
          <span className="bg-blue-100 text-blue-700 text-xs px-2 py-1 rounded-full">
            {leads.length} new
          </span>
        )}
      </div>

      {leads.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">
          No new lookalike leads. Win more deals to teach the AI.
        </p>
      ) : (
        <>
          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {leads.slice(0, 10).map((lead) => (
              <div
                key={lead.company_id}
                className="flex items-center gap-2 p-2 border rounded hover:bg-gray-50"
              >
                <input
                  type="checkbox"
                  checked={selected.includes(lead.company_id)}
                  onChange={() => toggleSelect(lead.company_id)}
                  className="rounded"
                />
                <div
                  className="flex-1 min-w-0 cursor-pointer"
                  onClick={() => onCompanyClick?.(lead.company_id)}
                >
                  <p className="text-sm font-medium truncate">{lead.name}</p>
                  <p className="text-xs text-gray-500">
                    {lead.city} · Similar to: {lead.lookalike_of}
                  </p>
                </div>
                <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                  ICP: {lead.icp_score}
                </span>
              </div>
            ))}
          </div>

          {selected.length > 0 && (
            <button
              onClick={handleApprove}
              className="mt-3 w-full py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700"
            >
              Approve {selected.length} leads for outreach
            </button>
          )}
        </>
      )}
    </div>
  );
}
