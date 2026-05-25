/**
 * ICPInsights Component
 * =======================
 * Shows "Your ICP learned 3 new patterns this week"
 * Displays learned patterns, adjustments, and negative signals.
 */
import React, { useState, useEffect } from 'react';
import { getICPInsights } from '../api';

export default function ICPInsights() {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInsights();
  }, []);

  const loadInsights = async () => {
    try {
      const res = await getICPInsights();
      setInsights(res.data);
    } catch (err) {
      console.error('Failed to load ICP insights:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="animate-pulse p-4">Loading...</div>;
  if (!insights) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <h2 className="text-lg font-bold text-gray-900 mb-3">
        ICP Learning Engine
      </h2>

      {/* Rating Stats */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="text-center p-2 bg-gray-50 rounded">
          <p className="text-lg font-bold">{insights.total_ratings}</p>
          <p className="text-xs text-gray-500">Leads rated</p>
        </div>
        <div className="text-center p-2 bg-green-50 rounded">
          <p className="text-lg font-bold text-green-700">{insights.good_leads_rated}</p>
          <p className="text-xs text-gray-500">Good (4-5★)</p>
        </div>
        <div className="text-center p-2 bg-red-50 rounded">
          <p className="text-lg font-bold text-red-700">{insights.bad_leads_rated}</p>
          <p className="text-xs text-gray-500">Bad (1-2★)</p>
        </div>
      </div>

      {/* Learning Status */}
      {!insights.ready_to_learn ? (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
          <p className="text-sm text-yellow-800">
            Rate more leads to teach the AI. Need 5+ good and 3+ bad ratings.
          </p>
          <div className="mt-2 bg-yellow-100 rounded-full h-2">
            <div
              className="bg-yellow-500 h-2 rounded-full"
              style={{ width: `${Math.min(100, (insights.total_ratings / 8) * 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <>
          {/* Learned Patterns */}
          {insights.patterns_learned?.length > 0 && (
            <div className="mb-3">
              <h3 className="text-sm font-semibold text-gray-700 mb-1">
                Patterns Learned
              </h3>
              <ul className="space-y-1">
                {insights.patterns_learned.map((pattern, i) => (
                  <li key={i} className="text-xs text-gray-600 flex items-start gap-1">
                    <span className="text-green-500 mt-0.5">✓</span>
                    {pattern}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Negative Signals */}
          {insights.negative_signals?.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-1">
                Negative Indicators
              </h3>
              <ul className="space-y-1">
                {insights.negative_signals.map((signal, i) => (
                  <li key={i} className="text-xs text-red-600 flex items-start gap-1">
                    <span>✗</span>
                    {signal}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {insights.last_updated && (
            <p className="text-xs text-gray-400 mt-3">
              Last updated: {new Date(insights.last_updated).toLocaleDateString()}
            </p>
          )}
        </>
      )}
    </div>
  );
}
