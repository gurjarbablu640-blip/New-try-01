/**
 * PipelineBoard Component
 * ========================
 * Kanban view: columns for each stage.
 * Card shows: company name, city, tier badge, ICP score, days in stage.
 * Red border on cards overdue for next_action.
 */
import React, { useState, useEffect } from 'react';
import { getPipelineBoard, movePipelineStage } from '../api';

const STAGES = [
  'New', 'Contacted', 'Replied', 'Meeting Booked',
  'Proposal Sent', 'Negotiation', 'Won', 'Nurture'
];

const STAGE_COLORS = {
  'New': 'border-t-gray-400',
  'Contacted': 'border-t-blue-400',
  'Replied': 'border-t-cyan-400',
  'Meeting Booked': 'border-t-green-400',
  'Proposal Sent': 'border-t-yellow-400',
  'Negotiation': 'border-t-orange-400',
  'Won': 'border-t-emerald-500',
  'Nurture': 'border-t-purple-400',
};

const TIER_BADGES = {
  'High-Value Recurring': { bg: 'bg-green-100', text: 'text-green-700', label: 'HVR' },
  'Compliance-Driven': { bg: 'bg-blue-100', text: 'text-blue-700', label: 'CD' },
  'Growth Potential': { bg: 'bg-purple-100', text: 'text-purple-700', label: 'GP' },
  'Low Potential': { bg: 'bg-gray-100', text: 'text-gray-500', label: 'LP' },
};

export default function PipelineBoard({ onCompanyClick }) {
  const [board, setBoard] = useState({});
  const [stageCounts, setStageCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [draggedCard, setDraggedCard] = useState(null);

  useEffect(() => {
    loadBoard();
  }, []);

  const loadBoard = async () => {
    try {
      const res = await getPipelineBoard();
      setBoard(res.data.board || {});
      setStageCounts(res.data.stage_counts || {});
    } catch (err) {
      console.error('Failed to load pipeline:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDragStart = (e, card) => {
    setDraggedCard(card);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = async (e, targetStage) => {
    e.preventDefault();
    if (!draggedCard || draggedCard.stage === targetStage) return;

    try {
      await movePipelineStage({
        company_id: draggedCard.company_id,
        stage: targetStage,
      });
      loadBoard(); // Refresh
    } catch (err) {
      console.error('Failed to move:', err);
    }
    setDraggedCard(null);
  };

  if (loading) {
    return <div className="animate-pulse p-4">Loading pipeline...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-bold text-gray-900">Pipeline</h2>
        <span className="text-sm text-gray-500">
          {Object.values(stageCounts).reduce((a, b) => a + b, 0)} deals
        </span>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-4">
        {STAGES.map((stage) => (
          <div
            key={stage}
            className={`min-w-[220px] flex-shrink-0 border-t-4 ${STAGE_COLORS[stage]} bg-gray-50 rounded-lg p-2`}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, stage)}
          >
            <div className="flex items-center justify-between mb-2 px-1">
              <h3 className="text-xs font-semibold text-gray-700 uppercase">{stage}</h3>
              <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded-full">
                {stageCounts[stage] || 0}
              </span>
            </div>

            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {(board[stage] || []).map((card) => (
                <PipelineCard
                  key={card.pipeline_id}
                  card={card}
                  onClick={() => onCompanyClick?.(card.company_id)}
                  onDragStart={(e) => handleDragStart(e, card)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PipelineCard({ card, onClick, onDragStart }) {
  const tier = TIER_BADGES[card.tier] || TIER_BADGES['Low Potential'];
  const isOverdue = card.is_overdue;

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      className={`bg-white rounded-md p-2 shadow-sm cursor-move hover:shadow-md transition-shadow border ${isOverdue ? 'border-red-400' : 'border-gray-200'}`}
    >
      <div className="flex items-start justify-between">
        <p className="font-medium text-xs text-gray-900 truncate flex-1">
          {card.company_name}
        </p>
        <span className="text-xs font-bold text-gray-600 ml-1">{card.icp_score}</span>
      </div>

      <p className="text-xs text-gray-500 truncate">{card.city}</p>

      <div className="mt-1 flex items-center gap-1">
        <span className={`text-xs px-1 py-0.5 rounded ${tier.bg} ${tier.text}`}>
          {tier.label}
        </span>
        <span className="text-xs text-gray-400 ml-auto">
          {card.days_in_stage}d
        </span>
      </div>

      {card.top_signal && (
        <p className="text-xs text-orange-600 mt-1 truncate">
          {card.top_signal.replace(/_/g, ' ').toLowerCase()}
        </p>
      )}
    </div>
  );
}
