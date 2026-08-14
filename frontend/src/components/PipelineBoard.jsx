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

export default function PipelineBoard({ onCompanyClick, locationFilter, compact }) {
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

  const [toasts, setToasts] = useState([]);

  const pushToast = (text, type='info') => {
    const id = Date.now() + Math.random();
    setToasts((t)=>[...t,{id,text,type}]);
    setTimeout(()=> setToasts((t)=>t.filter(x=>x.id!==id)), 5000);
  };

  const handleDrop = async (e, targetStage) => {
    e.preventDefault();
    if (!draggedCard || draggedCard.stage === targetStage) return;

    // optimistic update
    const prevBoard = JSON.parse(JSON.stringify(board));
    try {
      // remove from old stage
      const fromStage = draggedCard.stage;
      setBoard((b) => {
        const nb = {...b};
        nb[fromStage] = (nb[fromStage] || []).filter(c => c.pipeline_id !== draggedCard.pipeline_id);
        nb[targetStage] = [ {...draggedCard, stage: targetStage}, ...(nb[targetStage] || [])];
        return nb;
      });
      setStageCounts((sc)=>{ const n = {...sc}; n[fromStage]= (n[fromStage]||1)-1; n[targetStage]=(n[targetStage]||0)+1; return n; });

      // persist
      await movePipelineStage({
        company_id: draggedCard.company_id,
        stage: targetStage,
      });

      pushToast(`${draggedCard.company_name || 'Customer'} moved to ${targetStage}`, 'success');
    } catch (err) {
      // rollback
      setBoard(prevBoard);
      pushToast(`Failed to move ${draggedCard.company_name || 'customer'}: ${err?.message || 'Server error'}`, 'error');
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
              {(board[stage] || []).filter(card => {
                if (!locationFilter) return true;
                const city = (card.city || '').toLowerCase();
                const state = (card.state || '').toLowerCase();
                const filter = (locationFilter || '').toLowerCase();
                return city.includes(filter) || state.includes(filter);
              }).map((card) => (
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

  // Safely read fields with fallback
  const company = card.company_name || '--';
  const opportunity = card.opportunity_name || card.deal_name || card.name || '--';
  const value = card.estimated_value || card.value || card.deal_value || '--';
  const stage = card.stage || card.current_stage || '--';
  const contact = card.contact_name || card.primary_contact || '--';
  const designation = card.contact_designation || card.contact_title || '--';
  const email = card.contact_email || card.email || '--';
  const phone = card.contact_phone || card.phone || '--';
  const owner = card.owner_name || card.owner || '--';
  const leadScore = card.icp_score || card.lead_score || '--';
  const followup = card.next_action_date || card.follow_up || card.followup_date || '--';

  const [ownerOpen, setOwnerOpen] = React.useState(false);
  const [emailOpen, setEmailOpen] = React.useState(false);
  const [waOpen, setWaOpen] = React.useState(false);

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      className={`cursor-grab rounded-2xl border bg-white p-3 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md ${isOverdue ? 'border-red-200 bg-red-50/60' : 'border-slate-200'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className="flex-1 truncate text-sm font-semibold text-slate-800">{company}</p>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-600">{leadScore}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">{opportunity} · <span className="font-medium text-slate-700">{typeof value === 'number' ? `₹${Number(value).toLocaleString('en-IN')}` : value}</span></div>
          <div className="mt-2 text-xs text-slate-500">{stage} · {contact} {designation ? `· ${designation}` : ''}</div>
          <div className="mt-2 flex items-center justify-between">
            <div className="text-xs text-slate-500">{email}</div>
            <div className="text-xs text-slate-500">{phone}</div>
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            <button onClick={(e)=>{ e.stopPropagation(); const toObj = { email: card.contact_email || card.email, name: card.contact_name, phone: card.contact_phone, companyId: card.company_id }; window.dispatchEvent(new CustomEvent('openEmailComposer', { detail: toObj })); }} className="rounded-md p-2 hover:bg-slate-50" title="Email">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8m0 0v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>
            </button>
            <button onClick={(e)=>{ e.stopPropagation(); const toObj = { email: card.contact_email || card.email, name: card.contact_name, phone: card.contact_phone, companyId: card.company_id }; window.dispatchEvent(new CustomEvent('openWhatsAppComposer', { detail: toObj })); }} className="rounded-md p-2 hover:bg-slate-50" title="WhatsApp">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-green-600" viewBox="0 0 24 24" fill="currentColor"><path d="M16.7 13.3c-.3-.2-1.6-.8-1.9-.9-.5-.1-.9-.2-1.3.2-.4.3-1.5.9-2.1 1.1-.1 0-.6.1-1.1-.6-.4-.6-1.1-1.1-1.1-1.7 0-.6.4-.7.9-1.2.4-.5.5-.7.7-1 .2-.3 0-.5-.3-.8-.3-.3-1.3-1.2-1.8-1.6-.5-.4-.9-.3-1.3-.1-.4.2-1.6.6-2.4 2-.8 1.4-.3 3.2 0 3.9.3.7 2 3.3 4.8 4.7 3.2 1.6 4.2 1.1 4.9 1 .7-.1 2.1-.9 2.4-1.8.3-.9.3-1.6.2-1.8-.1-.2-.4-.3-.7-.5z"/></svg>
            </button>
            <div className="relative">
              <button onClick={(e)=>{ e.stopPropagation(); /* placeholder for more menu */ }} className="rounded-md p-2 hover:bg-slate-50" title="More">⋯</button>
            </div>
          </div>

          <div className="text-xs text-slate-500">Owner: <button onClick={(e)=>{ e.stopPropagation(); setOwnerOpen((o)=>!o); }} className="font-medium text-slate-700 hover:underline">{owner}</button></div>
          <div className="text-xs text-slate-500">Follow-up: {followup || '--'}</div>
        </div>
      </div>

      {ownerOpen && (
        <div className="absolute z-10 mt-2 w-40 rounded-md border bg-white p-2 shadow-md">
          <div className="text-sm font-semibold">{owner}</div>
          <div className="text-xs text-slate-500">{card.owner_role || '--'}</div>
          <div className="mt-2 text-xs">{card.owner_email || '--'}</div>
          <div className="text-xs">{card.owner_phone || '--'}</div>
        </div>
      )}

      {/* Email and WhatsApp drawers rendered at top-level by parent via state; for simplicity we expose events */}
    </div>
  );
}
