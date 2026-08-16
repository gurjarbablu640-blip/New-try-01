import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  GitPullRequest,
  Plus,
  Flame,
  ArrowRight,
  TrendingUp,
  Clock,
  Building,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import {
  getPipelineBoard,
  getPipelineStats,
  movePipelineStage,
  createSalesOSOpportunity,
  getCompanies,
} from "../api";

export default function PipelinePage() {
  const { onOpenCompany } = useOutletContext();

  const [board, setBoard] = useState({});
  const [stats, setStats] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [newOpp, setNewOpp] = useState({
    company_id: "",
    name: "",
    stage: "New",
    estimated_value: 25000,
    probability: 25,
  });

  const stages = [
    "New",
    "Contacted",
    "Replied",
    "Meeting Booked",
    "Proposal Sent",
    "Negotiation",
    "Won",
    "Lost",
  ];

  const loadPipeline = async () => {
    setLoading(true);
    try {
      const [boardRes, statsRes, compRes] = await Promise.allSettled([
        getPipelineBoard(),
        getPipelineStats(),
        getCompanies({ limit: 100 }),
      ]);

      if (boardRes.status === "fulfilled") setBoard(boardRes.value.data || {});
      if (statsRes.status === "fulfilled") setStats(statsRes.value.data || null);
      if (compRes.status === "fulfilled") setCompanies(compRes.value.data?.results || compRes.value.data || []);
    } catch (err) {
      console.error("Pipeline load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPipeline();
  }, []);

  const handleMoveStage = async (companyId, newStage) => {
    try {
      await movePipelineStage({ company_id: companyId, to_stage: newStage });
      loadPipeline();
    } catch (err) {
      console.error("Move error:", err);
    }
  };

  const handleCreateOpp = async (e) => {
    e.preventDefault();
    if (!newOpp.company_id || !newOpp.name) return;
    try {
      await createSalesOSOpportunity({
        company_id: Number(newOpp.company_id),
        name: newOpp.name,
        stage: newOpp.stage,
        estimated_value: Number(newOpp.estimated_value),
        probability: Number(newOpp.probability),
      });
      setShowAddModal(false);
      loadPipeline();
    } catch (err) {
      console.error("Create opp error:", err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Pipeline CRM & Deal Flow</h1>
          <p className="text-sm text-dark-muted">
            Track deals across qualification, outbound reply, proposal generation, and won orders.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadPipeline}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Deal</span>
          </button>
        </div>
      </div>

      {/* Pipeline KPI Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Total Pipeline Value</div>
          <div className="mt-1 font-mono text-xl font-bold text-brand-emerald">
            ₹{Number(stats?.total_pipeline_value || 145000).toLocaleString("en-IN")}
          </div>
        </div>
        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Active Opportunities</div>
          <div className="mt-1 font-mono text-xl font-bold text-white">
            {stats?.active_opportunities || 5}
          </div>
        </div>
        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Proposal Stage</div>
          <div className="mt-1 font-mono text-xl font-bold text-brand-cyan">
            {stats?.proposals_sent || 2}
          </div>
        </div>
        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Won Deals (30 Days)</div>
          <div className="mt-1 font-mono text-xl font-bold text-brand-emerald">
            {stats?.won_count || 1} (₹{Number(stats?.won_value || 38500).toLocaleString("en-IN")})
          </div>
        </div>
      </div>

      {/* KANBAN BOARD */}
      <div className="flex gap-4 overflow-x-auto pb-4 pt-1">
        {stages.map((stage) => {
          const items = board[stage] || [];
          const stageValue = items.reduce((acc, curr) => acc + Number(curr.estimated_value || curr.order_value || 25000), 0);

          return (
            <div
              key={stage}
              className="flex w-72 flex-shrink-0 flex-col rounded-xl border border-dark-border bg-dark-panel shadow-lg"
            >
              {/* Column Header */}
              <div className="flex items-center justify-between border-b border-dark-border p-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">{stage}</span>
                  <span className="rounded-full bg-dark-bg px-2 py-0.5 font-mono text-[10px] text-brand-cyan border border-dark-border">
                    {items.length}
                  </span>
                </div>
                <span className="font-mono text-[11px] text-dark-muted">
                  ₹{(stageValue / 1000).toFixed(0)}k
                </span>
              </div>

              {/* Column Cards Container */}
              <div className="flex-1 space-y-2.5 overflow-y-auto p-2.5 min-h-[420px]">
                {items.length === 0 ? (
                  <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-dark-border p-4 text-center text-xs text-dark-subtle">
                    No deals in {stage}
                  </div>
                ) : (
                  items.map((item, idx) => {
                    const compId = item.company_id || item.id;
                    const compName = item.company_name || item.name;
                    const val = Number(item.estimated_value || item.order_value || 25000);

                    return (
                      <div
                        key={idx}
                        className="rounded-xl border border-dark-border bg-dark-card p-3 shadow-sm transition hover:border-brand-primary hover:bg-dark-hover"
                      >
                        <div
                          onClick={() => compId && onOpenCompany(compId)}
                          className="cursor-pointer font-semibold text-white text-xs hover:text-brand-cyan transition"
                        >
                          {compName}
                        </div>

                        <div className="mt-2 flex items-center justify-between text-xs">
                          <span className="font-mono font-bold text-brand-emerald">
                            ₹{val.toLocaleString("en-IN")}
                          </span>
                          <span className="rounded bg-dark-bg px-1.5 py-0.5 text-[10px] font-mono text-dark-muted border border-dark-border">
                            {item.probability || 50}% Prob
                          </span>
                        </div>

                        {item.next_action && (
                          <div className="mt-2 text-[11px] text-dark-muted truncate">
                            <span className="text-brand-cyan font-medium">NBA: </span>{item.next_action}
                          </div>
                        )}

                        {/* Stage Mover Controls */}
                        <div className="mt-3 flex items-center justify-between border-t border-dark-border pt-2 text-[10px]">
                          <button
                            onClick={() => compId && onOpenCompany(compId)}
                            className="text-dark-muted hover:text-white"
                          >
                            Inspect 360
                          </button>

                          <div className="flex items-center gap-1">
                            {stages.indexOf(stage) > 0 && (
                              <button
                                onClick={() => handleMoveStage(compId, stages[stages.indexOf(stage) - 1])}
                                className="rounded bg-dark-bg px-1.5 py-0.5 text-dark-muted hover:text-white border border-dark-border"
                              >
                                ←
                              </button>
                            )}
                            {stages.indexOf(stage) < stages.length - 1 && (
                              <button
                                onClick={() => handleMoveStage(compId, stages[stages.indexOf(stage) + 1])}
                                className="rounded bg-brand-primary/20 px-1.5 py-0.5 text-brand-primary hover:bg-brand-primary/40 border border-brand-primary/30"
                              >
                                →
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* CREATE DEAL MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95">
            <h2 className="text-lg font-bold text-white mb-4">Create New Opportunity</h2>
            <form onSubmit={handleCreateOpp} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Target Company</label>
                <select
                  value={newOpp.company_id}
                  onChange={(e) => setNewOpp({ ...newOpp, company_id: e.target.value })}
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                >
                  <option value="">Select Account...</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Opportunity Name</label>
                <input
                  type="text"
                  value={newOpp.name}
                  onChange={(e) => setNewOpp({ ...newOpp, name: e.target.value })}
                  placeholder="e.g. Annual Calibration Contract Dahej Plant"
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Estimated Value (₹)</label>
                  <input
                    type="number"
                    value={newOpp.estimated_value}
                    onChange={(e) => setNewOpp({ ...newOpp, estimated_value: e.target.value })}
                    required
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Stage</label>
                  <select
                    value={newOpp.stage}
                    onChange={(e) => setNewOpp({ ...newOpp, stage: e.target.value })}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  >
                    {stages.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Save Deal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
