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
      loadBoard();
    } catch (err) {
      console.error('Failed to move:', err);
    }
    setDraggedCard(null);
  };

  if (loading) {
    return <div className="rounded-2xl border border-slate-200 bg-white p-6 text-slate-500 shadow-sm">Loading pipeline...</div>;
  }

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-600">Kanban board</p>
          <h2 className="mt-1 text-2xl font-bold text-slate-900">Pipeline</h2>
        </div>
        <div className="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-600">
          {Object.values(stageCounts).reduce((a, b) => a + b, 0)} deals
        </div>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-3">
        {STAGES.map((stage) => (
          <div
            key={stage}
            className={`min-w-[240px] flex-shrink-0 rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-inner ${STAGE_COLORS[stage]}`}
            onDragOver={handleDragOver}
            onDrop={(e) => handleDrop(e, stage)}
          >
            <div className="mb-3 flex items-center justify-between rounded-xl bg-white/80 px-2.5 py-2 shadow-sm">
              <h3 className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-600">{stage}</h3>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                {stageCounts[stage] || 0}
              </span>
            </div>

            <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
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
      className={`cursor-grab rounded-2xl border bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${isOverdue ? 'border-red-200 bg-red-50/60' : 'border-slate-200'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="flex-1 truncate text-sm font-semibold text-slate-800">{card.company_name}</p>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{card.icp_score}</span>
      </div>

      <p className="mt-2 text-xs text-slate-500">{card.city}</p>

      <div className="mt-3 flex items-center justify-between gap-2">
        <span className={`rounded-full px-2 py-1 text-[10px] font-semibold ${tier.bg} ${tier.text}`}>
          {tier.label}
        </span>
        <span className="text-[10px] font-medium text-slate-400">{card.days_in_stage}d</span>
      </div>

      {card.top_signal && (
        <p className="mt-2 truncate text-[11px] font-medium text-amber-700">
          {card.top_signal.replace(/_/g, ' ').toLowerCase()}
        </p>
      )}
    </div>
  );
}
