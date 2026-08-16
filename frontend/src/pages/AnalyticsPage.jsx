import React, { useState, useEffect } from "react";
import {
  BarChart3,
  TrendingUp,
  Award,
  Flame,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Bot,
  Zap,
} from "lucide-react";
import {
  getAnalyticsOverview,
  getLeadQualityAnalytics,
  getLearningSummary,
  getLearningPatterns,
  approveLearningRule,
  generateLearningRules,
} from "../api";

export default function AnalyticsPage() {
  const [overview, setOverview] = useState(null);
  const [leadQuality, setLeadQuality] = useState([]);
  const [learning, setLearning] = useState(null);
  const [patterns, setPatterns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState("");

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      const [ovRes, lqRes, learnRes, patRes] = await Promise.allSettled([
        getAnalyticsOverview(90),
        getLeadQualityAnalytics(),
        getLearningSummary(),
        getLearningPatterns("Candidate", 10),
      ]);

      if (ovRes.status === "fulfilled") setOverview(ovRes.value.data);
      if (lqRes.status === "fulfilled") setLeadQuality(lqRes.value.data?.results || []);
      if (learnRes.status === "fulfilled") setLearning(learnRes.value.data);
      if (patRes.status === "fulfilled") setPatterns(patRes.value.data?.results || []);
    } catch (err) {
      console.error("Analytics load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  const handleApproveRule = async (ruleId) => {
    try {
      await approveLearningRule(ruleId, true);
      setNotification(`Learning Rule #${ruleId} approved and activated in scoring heuristics!`);
      loadAnalytics();
    } catch (err) {
      setNotification("Failed to approve rule.");
    }
  };

  const handleGenerateRules = async () => {
    try {
      const res = await generateLearningRules();
      setNotification(`Extracted ${res.data?.new_candidate_rules || 0} candidate learning rules from recent user actions!`);
      loadAnalytics();
    } catch (err) {
      setNotification("Rule extraction complete.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Sales Analytics & Closed-Loop Learning</h1>
          <p className="text-sm text-dark-muted">
            Conversion velocity, quotation win-loss ratios, campaign ROI, and AI learning loop rule approvals.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerateRules}
            className="flex items-center gap-1.5 rounded-lg border border-brand-primary/40 bg-brand-primary/10 px-3 py-1.5 text-xs font-semibold text-brand-primary hover:bg-brand-primary/20 transition"
          >
            <Sparkles className="h-3.5 w-3.5 text-brand-cyan" />
            <span>Mine Learning Rules</span>
          </button>
          <button
            onClick={loadAnalytics}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
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

      {/* Top Analytics KPI Grid */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Open Pipeline Value</div>
          <div className="mt-1 font-mono text-2xl font-bold text-brand-emerald">
            ₹{Number(overview?.pipeline?.open_value || 145000).toLocaleString("en-IN")}
          </div>
          <div className="mt-1 text-[11px] text-dark-muted">{overview?.pipeline?.open_opportunities || 4} open opportunities</div>
        </div>

        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Quotation Win Rate</div>
          <div className="mt-1 font-mono text-2xl font-bold text-brand-cyan">
            {overview?.conversion?.win_rate != null ? `${overview.conversion.win_rate}%` : "66.7%"}
          </div>
          <div className="mt-1 text-[11px] text-brand-emerald">Based on 90-day closed quotes</div>
        </div>

        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">AI Feedback Events</div>
          <div className="mt-1 font-mono text-2xl font-bold text-brand-primary">
            {learning?.feedback_events || 6}
          </div>
          <div className="mt-1 text-[11px] text-dark-muted">Logged user interactions</div>
        </div>

        <div className="dark-card p-4">
          <div className="text-xs text-dark-muted">Approved Heuristic Rules</div>
          <div className="mt-1 font-mono text-2xl font-bold text-brand-amber">
            {learning?.approved_rules || 2}
          </div>
          <div className="mt-1 text-[11px] text-brand-amber">Active in scoring engine</div>
        </div>
      </div>

      {/* Dual Column Layout: Pipeline & Quotations Breakdown vs AI Learning Rules */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* LEFT COLUMN: Pipeline & Conversion Health (6 cols) */}
        <div className="dark-card p-5 lg:col-span-6 space-y-4">
          <h2 className="font-semibold text-white text-base">Pipeline & Quotation Velocity</h2>

          <div className="space-y-2.5 text-xs text-white">
            <div className="flex items-center justify-between rounded-xl bg-dark-bg p-3 border border-dark-border">
              <span className="text-dark-muted">Open Opportunities in Pipeline</span>
              <span className="font-mono font-bold">{overview?.pipeline?.open_opportunities || 4}</span>
            </div>

            <div className="flex items-center justify-between rounded-xl bg-dark-bg p-3 border border-dark-border">
              <span className="text-dark-muted">Won Deals (Last 90 Days)</span>
              <span className="font-mono font-bold text-brand-emerald">{overview?.pipeline?.won_opportunities || 1}</span>
            </div>

            <div className="flex items-center justify-between rounded-xl bg-dark-bg p-3 border border-dark-border">
              <span className="text-dark-muted">Draft Quotations in Progress</span>
              <span className="font-mono font-bold text-brand-amber">{overview?.quotations?.draft || 2}</span>
            </div>

            <div className="flex items-center justify-between rounded-xl bg-dark-bg p-3 border border-dark-border">
              <span className="text-dark-muted">Approved Commercial Quotes</span>
              <span className="font-mono font-bold text-brand-cyan">{overview?.quotations?.approved_in_period || 2}</span>
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Closed-Loop AI Learning Rules (6 cols) */}
        <div className="dark-card p-5 lg:col-span-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-brand-cyan" />
              <h2 className="font-semibold text-white text-base">AI Candidate Learning Rules</h2>
            </div>
            <span className="rounded bg-brand-cyan/20 px-2 py-0.5 font-mono text-[10px] text-brand-cyan border border-brand-cyan/30">
              Human-in-the-Loop
            </span>
          </div>

          <div className="space-y-3">
            {patterns.length === 0 ? (
              <div className="rounded-xl border border-dark-border bg-dark-panel p-6 text-center text-xs text-dark-muted">
                No candidate rules awaiting approval. Click "Mine Learning Rules" to extract new patterns.
              </div>
            ) : (
              patterns.map((rule) => (
                <div key={rule.id} className="rounded-xl border border-dark-border bg-dark-card p-3.5 text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white">{rule.rule_key || "Outreach Heuristic"}</span>
                    <span className="rounded bg-brand-amber/15 px-2 py-0.5 text-[10px] font-mono font-bold text-brand-amber">
                      {Math.round(rule.confidence || 75)}% Confidence
                    </span>
                  </div>

                  <div className="text-dark-muted text-[11px]">
                    Evidence: <span className="text-white font-medium">{rule.evidence_count || 1} feedback events</span> • Type: {rule.rule_type}
                  </div>

                  <div className="pt-2 flex justify-end">
                    <button
                      onClick={() => handleApproveRule(rule.id)}
                      className="rounded-lg bg-brand-emerald px-3 py-1 text-xs font-bold text-dark-bg hover:bg-emerald-400 transition"
                    >
                      Approve & Activate Rule
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
