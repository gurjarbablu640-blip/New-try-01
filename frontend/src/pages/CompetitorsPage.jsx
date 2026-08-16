import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  Plus,
  Flame,
  CheckCircle2,
  RefreshCw,
  Zap,
  Target,
  Award,
  AlertTriangle,
  Building,
} from "lucide-react";
import {
  getCompetitors,
  seedDefaultCompetitors,
  getCompetitorObservations,
  createCompetitorObservation,
  getCompanies,
} from "../api";

export default function CompetitorsPage() {
  const [competitors, setCompetitors] = useState([]);
  const [observations, setObservations] = useState([]);
  const [selectedCompetitor, setSelectedCompetitor] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState("");
  const [showObsModal, setShowObsModal] = useState(false);

  const [newObs, setNewObs] = useState({
    company_id: "",
    competitor_id: "",
    observation_type: "Pricing",
    title: "Competitor Underbidding on Thermal Audits",
    evidence: "Client showed competitor quote offering 15% discount for 30-day turnaround.",
    impact: "Medium",
  });

  const loadCompetitorData = async () => {
    setLoading(true);
    try {
      const [compRes, obsRes, coRes] = await Promise.allSettled([
        getCompetitors(),
        getCompetitorObservations({ limit: 50 }),
        getCompanies({ limit: 100 }),
      ]);

      if (compRes.status === "fulfilled") {
        const list = compRes.value.data?.results || compRes.value.data || [];
        setCompetitors(list);
        if (list.length > 0) setSelectedCompetitor(list[0]);
      }
      if (obsRes.status === "fulfilled") {
        setObservations(obsRes.value.data?.results || obsRes.value.data || []);
      }
      if (coRes.status === "fulfilled") {
        setCompanies(coRes.value.data?.results || coRes.value.data || []);
      }
    } catch (err) {
      console.error("Competitor load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCompetitorData();
  }, []);

  const handleSeedDefaults = async () => {
    try {
      const res = await seedDefaultCompetitors();
      setNotification(`Seeded ${res.data?.total_competitors_added || 3} Gujarat regional competitor battlecards!`);
      loadCompetitorData();
    } catch (err) {
      setNotification("Competitors already seeded or error occurred.");
    }
  };

  const handleCreateObservation = async (e) => {
    e.preventDefault();
    if (!newObs.company_id || !newObs.title) return;
    try {
      await createCompetitorObservation({
        company_id: Number(newObs.company_id),
        competitor_id: newObs.competitor_id ? Number(newObs.competitor_id) : null,
        observation_type: newObs.observation_type,
        title: newObs.title,
        evidence: newObs.evidence,
        impact: newObs.impact,
      });
      setShowObsModal(false);
      setNotification("Competitor observation recorded in account intel!");
      loadCompetitorData();
    } catch (err) {
      setNotification("Failed to record observation.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Competitor Intelligence & Battlecards</h1>
          <p className="text-sm text-dark-muted">
            Gujarat regional testing incumbents, pricing strategies, turnaround vulnerabilities, and Oorja winning angles.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleSeedDefaults}
            className="flex items-center gap-1.5 rounded-lg border border-brand-primary/40 bg-brand-primary/10 px-3 py-1.5 text-xs font-semibold text-brand-primary hover:bg-brand-primary/20 transition"
          >
            <Zap className="h-3.5 w-3.5 text-brand-cyan" />
            <span>Seed Gujarat Competitors</span>
          </button>
          <button
            onClick={() => setShowObsModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Log Field Observation</span>
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div className="rounded-xl border border-brand-emerald/30 bg-brand-emerald/10 px-4 py-3 text-xs text-brand-emerald flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Dual Pane Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-220px)]">
        {/* LEFT COLUMN: Competitor Directory (4 cols) */}
        <div className="dark-card p-3 lg:col-span-4 flex flex-col space-y-2 overflow-y-auto">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-dark-muted">
            Known Incumbents ({competitors.length})
          </div>

          {competitors.length === 0 ? (
            <div className="p-8 text-center text-xs text-dark-muted">
              No competitor profiles loaded. Click "Seed Gujarat Competitors" above.
            </div>
          ) : (
            competitors.map((comp) => {
              const isSelected = selectedCompetitor?.id === comp.id;

              return (
                <div
                  key={comp.id}
                  onClick={() => setSelectedCompetitor(comp)}
                  className={`cursor-pointer rounded-xl p-3.5 text-xs transition border ${
                    isSelected
                      ? "bg-brand-primary/15 border-brand-primary/40 shadow-sm"
                      : "border-dark-border bg-dark-card hover:bg-dark-hover"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white text-sm">{comp.name}</span>
                    <span className="rounded bg-brand-amber/15 px-2 py-0.5 text-[10px] font-mono text-brand-amber border border-brand-amber/30">
                      {comp.region || "Gujarat"}
                    </span>
                  </div>

                  <div className="mt-1 text-dark-muted text-[11px]">
                    Turnaround: <span className="text-white font-medium">{comp.turnaround_days || "10–14"} days</span>
                  </div>

                  <div className="mt-2 text-xs text-white/80 line-clamp-2">
                    {comp.pricing_notes || "Standard corporate pricing structure"}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* RIGHT COLUMN: Full Battlecard & Counter-Pitch (8 cols) */}
        <div className="dark-card p-5 lg:col-span-8 flex flex-col overflow-y-auto space-y-5">
          {!selectedCompetitor ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              Select a competitor from the directory to inspect strengths, vulnerabilities, and winning pitches.
            </div>
          ) : (
            <>
              {/* Header */}
              <div className="flex items-start justify-between pb-4 border-b border-dark-border">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-white">{selectedCompetitor.name}</h2>
                    <span className="badge-primary rounded px-2 py-0.5 text-xs">
                      {selectedCompetitor.region || "Gujarat Region"}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-dark-muted">
                    Typical Turnaround: <span className="font-semibold text-brand-amber">{selectedCompetitor.turnaround_days || "10–14"} Days</span> (Oorja Advantage: 48 Hours)
                  </div>
                </div>
              </div>

              {/* Strengths vs Weaknesses Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-xl border border-dark-border bg-dark-card p-4 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold uppercase text-brand-cyan">
                    <Target className="h-4 w-4" />
                    <span>Observed Strengths</span>
                  </div>
                  <p className="text-xs text-white/90 leading-relaxed">
                    {selectedCompetitor.strengths || "Established legacy brand with long-term vendor contracts in Dahej chemical estates."}
                  </p>
                </div>

                <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold uppercase text-red-400">
                    <AlertTriangle className="h-4 w-4" />
                    <span>Vulnerabilities / Weaknesses</span>
                  </div>
                  <p className="text-xs text-white/90 leading-relaxed">
                    {selectedCompetitor.weaknesses || "Slow 10-14 day turnarounds cause plant downtime. Rigid pricing and slow certificate deliveries."}
                  </p>
                </div>
              </div>

              {/* Oorja Winning Strategy Battlecard */}
              <div className="rounded-xl border border-brand-emerald/40 bg-gradient-to-br from-brand-emerald/15 via-dark-panel to-dark-panel p-5 shadow-lg space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand-emerald">
                  <Award className="h-5 w-5" />
                  <span>Oorja Sales Winning Angle & Counter-Pitch</span>
                </div>
                <div className="text-sm font-semibold text-white">
                  "Guaranteed 48-Hour On-Site Turnaround + Instant Digital NABL Certificates"
                </div>
                <p className="text-xs text-dark-muted leading-relaxed">
                  When facing {selectedCompetitor.name}, highlight that plant downtime costs far exceed calibration fees. Oorja's dedicated Gujarat on-site team delivers complete NABL calibration within 48 hours, eliminating shipping risks and production delays.
                </p>
              </div>

              {/* Recent Field Observations */}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Recent Field Observations ({observations.length})
                </div>
                <div className="space-y-2">
                  {observations.length === 0 ? (
                    <div className="rounded-xl border border-dark-border bg-dark-panel p-4 text-center text-xs text-dark-muted">
                      No field observations logged for this competitor yet.
                    </div>
                  ) : (
                    observations.map((obs) => (
                      <div key={obs.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                        <div className="flex items-center justify-between font-semibold text-white">
                          <span>{obs.title}</span>
                          <span className="font-mono text-dark-muted text-[10px]">{obs.created_at?.slice(0, 10)}</span>
                        </div>
                        <div className="mt-1 text-dark-muted">{obs.evidence}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* LOG OBSERVATION MODAL */}
      {showObsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95">
            <h2 className="text-lg font-bold text-white mb-4">Log Competitor Field Observation</h2>
            <form onSubmit={handleCreateObservation} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Customer Account</label>
                <select
                  value={newObs.company_id}
                  onChange={(e) => setNewObs({ ...newObs, company_id: e.target.value })}
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
                <label className="block text-dark-muted mb-1 font-medium">Competitor (Optional)</label>
                <select
                  value={newObs.competitor_id}
                  onChange={(e) => setNewObs({ ...newObs, competitor_id: e.target.value })}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                >
                  <option value="">Select Competitor...</option>
                  {competitors.map((cp) => (
                    <option key={cp.id} value={cp.id}>{cp.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Observation Title</label>
                <input
                  type="text"
                  value={newObs.title}
                  onChange={(e) => setNewObs({ ...newObs, title: e.target.value })}
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Evidence / Details</label>
                <textarea
                  value={newObs.evidence}
                  onChange={(e) => setNewObs({ ...newObs, evidence: e.target.value })}
                  rows={2}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowObsModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Save Observation
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
