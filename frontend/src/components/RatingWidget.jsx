/**
 * RatingWidget Component
 * ========================
 * 1-5 star rating + reason on CompanyDrawer.
 * Feeds data into ICP Learning Engine.
 */
import React, { useState } from 'react';
import { rateLead } from '../api';

const REASONS = [
  'Perfect fit',
  'Good industry match',
  'Right size & certs',
  'Wrong industry',
  'Too small',
  'Trading company',
  'No calibration need',
  'Other',
];

export default function RatingWidget({ companyId, currentRating, onRated }) {
  const [rating, setRating] = useState(currentRating || 0);
  const [hoveredStar, setHoveredStar] = useState(0);
  const [reason, setReason] = useState('');
  const [showReasons, setShowReasons] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleRate = async (stars) => {
    setRating(stars);
    setShowReasons(true);
  };

  const submitRating = async () => {
    setSaving(true);
    try {
      await rateLead(companyId, rating, reason);
      setSaved(true);
      onRated?.(rating);
      setTimeout(() => {
        setShowReasons(false);
        setSaved(false);
      }, 2000);
    } catch (err) {
      console.error('Rating error:', err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border rounded-md p-3 bg-gray-50">
      <p className="text-xs font-semibold text-gray-600 mb-2">Rate this lead</p>

      {/* Stars */}
      <div className="flex items-center gap-1">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            onClick={() => handleRate(star)}
            onMouseEnter={() => setHoveredStar(star)}
            onMouseLeave={() => setHoveredStar(0)}
            className="text-xl transition-transform hover:scale-110"
          >
            {star <= (hoveredStar || rating) ? '★' : '☆'}
          </button>
        ))}
        {rating > 0 && (
          <span className="text-xs text-gray-500 ml-2">
            {rating >= 4 ? 'Good fit' : rating <= 2 ? 'Poor fit' : 'Average'}
          </span>
        )}
      </div>

      {/* Reason Selector */}
      {showReasons && !saved && (
        <div className="mt-2">
          <div className="flex flex-wrap gap-1 mb-2">
            {REASONS.map((r) => (
              <button
                key={r}
                onClick={() => setReason(r)}
                className={`text-xs px-2 py-1 rounded border ${
                  reason === r
                    ? 'bg-blue-100 border-blue-300 text-blue-700'
                    : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-100'
                }`}
              >
                {r}
              </button>
            ))}
          </div>
          <button
            onClick={submitRating}
            disabled={saving}
            className="w-full py-1.5 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Submit Rating'}
          </button>
        </div>
      )}

      {saved && (
        <p className="text-xs text-green-600 mt-2">
          Rating saved! This helps the AI learn your ICP.
        </p>
      )}
    </div>
  );
}
