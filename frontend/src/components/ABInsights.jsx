/**
 * ABInsights Component
 * =====================
 * Bar chart: subject line variants vs reply rate.
 * Best pattern summary.
 */
import React, { useState, useEffect } from 'react';
import { getABInsights } from '../api';

const VARIANT_LABELS = {
  1: 'Instrument-specific',
  2: 'Certification-focused',
  3: 'Question format',
  4: 'Urgency/trigger',
  5: 'Benefit-led',
};

export default function ABInsights() {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInsights();
  }, []);

  const loadInsights = async () => {
    try {
      const res = await getABInsights();
      setInsights(res.data);
    } catch (err) {
      console.error('Failed to load A/B insights:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div className="animate-pulse p-4">Loading A/B data...</div>;
  if (!insights) return null;

  const variantStats = insights.variant_stats || {};
  const maxRate = Math.max(
    ...Object.values(variantStats).map(s => s.reply_rate || 0),
    1
  );

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <h2 className="text-lg font-bold text-gray-900 mb-3">
        Subject Line A/B Performance
      </h2>

      {/* Overall Stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="text-center p-2 bg-gray-50 rounded">
          <p className="text-lg font-bold text-gray-900">{insights.total_tests}</p>
          <p className="text-xs text-gray-500">Emails tracked</p>
        </div>
        <div className="text-center p-2 bg-gray-50 rounded">
          <p className="text-lg font-bold text-green-600">{insights.overall_open_rate}%</p>
          <p className="text-xs text-gray-500">Open rate</p>
        </div>
        <div className="text-center p-2 bg-gray-50 rounded">
          <p className="text-lg font-bold text-blue-600">{insights.overall_reply_rate}%</p>
          <p className="text-xs text-gray-500">Reply rate</p>
        </div>
      </div>

      {/* Bar Chart */}
      <div className="space-y-3 mb-4">
        {Object.entries(variantStats).map(([variant, stats]) => (
          <div key={variant} className="flex items-center gap-2">
            <span className="text-xs text-gray-600 w-32 truncate">
              {VARIANT_LABELS[variant] || `Variant ${variant}`}
            </span>
            <div className="flex-1 bg-gray-100 rounded-full h-5 relative">
              <div
                className="bg-blue-500 h-5 rounded-full transition-all"
                style={{ width: `${(stats.reply_rate / maxRate) * 100}%` }}
              />
              <span className="absolute right-2 top-0.5 text-xs text-gray-700">
                {stats.reply_rate}%
              </span>
            </div>
            <span className="text-xs text-gray-400 w-12">
              n={stats.total_sent}
            </span>
          </div>
        ))}
      </div>

      {/* Winning Pattern */}
      {insights.winning_pattern && (
        <div className="bg-green-50 border border-green-200 rounded-md p-3">
          <p className="text-sm font-medium text-green-800">
            Winner: {insights.winning_pattern}
          </p>
          <p className="text-xs text-green-700 mt-1">
            {insights.recommendation}
          </p>
        </div>
      )}

      {insights.total_tests < 10 && (
        <p className="text-xs text-gray-400 mt-2 text-center">
          Need {10 - insights.total_tests} more tracked emails for meaningful analysis
        </p>
      )}
    </div>
  );
}
