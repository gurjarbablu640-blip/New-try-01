import React, { useState, useEffect } from "react";
import { useOutletContext, useNavigate } from "react-router-dom";
import {
  Users,
  Flame,
  Gauge,
  FileText,
  GitPullRequest,
  TrendingUp,
  Bot,
  ArrowUpRight,
  Clock,
  Send,
  AlertCircle,
  CheckCircle2,
  Calendar,
  Sparkles,
  ChevronRight,
  Building,
} from "lucide-react";
import {
  getSalesOSSummary,
  getSalesOSOpportunities,
  getSalesOSQuotations,
  getCalibrationDue,
  getBuyingWindow,
  getInboxReplies,
  askOorjaAI,
} from "../api";

export default function DashboardPage() {
  const { onOpenCompany } = useOutletContext();
  const navigate = useNavigate();

  const [summary, setSummary] = useState(null);
  const [opportunities, setOpportunities] = useState([]);
  const [quotations, setQuotations] = useState([]);
  const [calibrationsDue, setCalibrationsDue] = useState([]);
  const [buyingWindows, setBuyingWindows] = useState([]);
  const [recentReplies, setRecentReplies] = useState([]);
  const [quickQuestion, setQuickQuestion] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadDashboard = async () => {
      setLoading(true);
      try {
        const [sumRes, oppRes, quoteRes, calRes, bwRes, repRes] = await Promise.allSettled([
          getSalesOSSummary(),
          getSalesOSOpportunities({ limit: 5 }),
          getSalesOSQuotations({ limit: 5 }),
          getCalibrationDue({ days: 45, limit: 5 }),
          getBuyingWindow(),
          getInboxReplies({ limit: 4 }),
        ]);

        if (sumRes.status === "fulfilled") setSummary(sumRes.value.data);
        if (oppRes.status === "fulfilled") setOpportunities(oppRes.value.data?.results || oppRes.value.data || []);
        if (quoteRes.status === "fulfilled") setQuotations(quoteRes.value.data?.results || quoteRes.value.data || []);
        if (calRes.status === "fulfilled") setCalibrationsDue(calRes.value.data?.results || calRes.value.data || []);
        if (bwRes.status === "fulfilled") setBuyingWindows(bwRes.value.data?.results || bwRes.value.data || []);
        if (repRes.status === "fulfilled") setRecentReplies(repRes.value.data?.results || repRes.value.data || []);
      } catch (err) {
        console.error("Dashboard load error:", err);
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();
  }, []);

  const handleAskQuickAI = async (e) => {
    e.preventDefault();
    if (!quickQuestion.trim()) return;
    setAiLoading(true);
    try {
      const res = await askOorjaAI(quickQuestion);
      setAiAnswer(res.data?.answer || "No response generated.");
    } catch (err) {
      setAiAnswer("Failed to process question via Ask Oorja.");
    } finally {
      setAiLoading(false);
    }
  };

  const totalPipelineVal = summary?.open_pipeline_value || 125000;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Command Center</h1>
          <p className="text-sm text-dark-muted">
            Real-time executive cockpit for calibration sales & industrial outreach.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate("/assistant")}
            className="flex items-center gap-1.5 rounded-lg border border-brand-primary/40 bg-brand-primary/10 px-3 py-1.5 text-xs font-semibold text-brand-primary transition hover:bg-brand-primary/20"
          >
            <Bot className="h-3.5 w-3.5 text-brand-cyan" />
            <span>AI Workspace</span>
          </button>
          <button
            onClick={() => navigate("/pipeline")}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-primaryHover"
          >
            <GitPullRequest className="h-3.5 w-3.5" />
            <span>Open Pipeline</span>
          </button>
        </div>
      </div>

      {/* TOP KPI STRIP */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="dark-card p-4">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>New Leads</span>
            <Users className="h-4 w-4 text-brand-cyan" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-white">
            {summary?.leads_count || 12}
          </div>
          <div className="mt-1 text-[11px] text-brand-emerald flex items-center gap-0.5">
            <span>+4 this week</span>
          </div>
        </div>

        <div className="dark-card p-4">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>Qualified Leads</span>
            <Flame className="h-4 w-4 text-brand-amber" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-white">
            {summary?.qualified_leads || 8}
          </div>
          <div className="mt-1 text-[11px] text-brand-amber flex items-center gap-0.5">
            <span>Ready for outreach</span>
          </div>
        </div>

        <div className="dark-card p-4">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>Campaign Replies</span>
            <Send className="h-4 w-4 text-brand-secondary" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-white">
            {recentReplies.length || 3}
          </div>
          <div className="mt-1 text-[11px] text-brand-emerald">
            100% Inbound Match
          </div>
        </div>

        <div className="dark-card p-4">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>Open Opportunities</span>
            <GitPullRequest className="h-4 w-4 text-brand-primary" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-white">
            {summary?.open_opportunities || opportunities.length || 4}
          </div>
          <div className="mt-1 text-[11px] text-dark-muted">
            In active negotiation
          </div>
        </div>

        <div className="dark-card p-4">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>Active Quotations</span>
            <FileText className="h-4 w-4 text-brand-cyan" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-white">
            {summary?.open_quotations || quotations.length || 3}
          </div>
          <div className="mt-1 text-[11px] text-brand-cyan">
            With version control
          </div>
        </div>

        <div className="dark-card p-4 bg-gradient-to-br from-dark-panel via-dark-panel to-brand-primary/10 border-brand-primary/30">
          <div className="flex items-center justify-between text-dark-muted text-xs">
            <span>Pipeline Value</span>
            <TrendingUp className="h-4 w-4 text-brand-emerald" />
          </div>
          <div className="mt-2 font-mono text-2xl font-bold text-brand-emerald">
            ₹{Number(totalPipelineVal).toLocaleString("en-IN")}
          </div>
          <div className="mt-1 text-[11px] text-brand-emerald">
            Active pipeline
          </div>
        </div>
      </div>

      {/* QUICK ASK OORJA BAR */}
      <div className="rounded-xl border border-brand-primary/40 bg-gradient-to-r from-dark-panel via-brand-primary/10 to-dark-panel p-4 shadow-lg">
        <form onSubmit={handleAskQuickAI} className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-primary/20 text-brand-cyan border border-brand-cyan/30 flex-shrink-0">
            <Bot className="h-5 w-5" />
          </div>
          <input
            type="text"
            value={quickQuestion}
            onChange={(e) => setQuickQuestion(e.target.value)}
            placeholder="Ask Oorja AI: 'Who should I contact today?' or 'Is Bourdon gauge within NABL scope?'"
            className="flex-1 rounded-lg border border-dark-border bg-[#0E1523] px-4 py-2 text-sm text-white placeholder-dark-muted focus:border-brand-cyan focus:outline-none"
          />
          <button
            type="submit"
            disabled={aiLoading}
            className="rounded-lg bg-brand-primary px-4 py-2 text-xs font-semibold text-white shadow transition hover:bg-brand-primaryHover disabled:opacity-50"
          >
            {aiLoading ? "Thinking..." : "Ask AI"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/assistant")}
            className="rounded-lg border border-dark-border bg-dark-card px-3 py-2 text-xs text-dark-muted hover:text-white"
          >
            Full AI Studio
          </button>
        </form>

        {aiAnswer && (
          <div className="mt-3 rounded-lg border border-brand-cyan/30 bg-[#0E1523]/80 p-3 text-xs text-white whitespace-pre-line animate-in fade-in duration-200">
            <span className="font-semibold text-brand-cyan">Oorja AI Response: </span>
            {aiAnswer}
          </div>
        )}
      </div>

      {/* MAIN TWO-COLUMN SPLIT */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* LEFT COLUMN: Priority Actions & Daily Radar (7 cols) */}
        <div className="space-y-6 lg:col-span-7">
          {/* Priority Actions */}
          <div className="dark-card p-5">
            <div className="flex items-center justify-between pb-3 border-b border-dark-border">
              <div className="flex items-center gap-2">
                <Flame className="h-5 w-5 text-brand-amber" />
                <h2 className="font-semibold text-white text-base">Priority Action Queue</h2>
              </div>
              <span className="rounded bg-brand-amber/15 px-2 py-0.5 text-xs font-mono text-brand-amber border border-brand-amber/30">
                Action Required
              </span>
            </div>

            <div className="mt-4 space-y-3">
              <div
                onClick={() => navigate("/leads")}
                className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3.5 transition hover:border-brand-primary hover:bg-dark-hover"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-emerald/15 text-brand-emerald border border-brand-emerald/30">
                    <Users className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="font-medium text-white text-sm">8 Qualified Leads Ready for Campaign Dispatch</div>
                    <div className="text-xs text-dark-muted">Verified decision-makers in Dahej & Hazira chemical corridors</div>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-dark-muted" />
              </div>

              <div
                onClick={() => navigate("/inbox")}
                className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3.5 transition hover:border-brand-primary hover:bg-dark-hover"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-primary/15 text-brand-primary border border-brand-primary/30">
                    <Send className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="font-medium text-white text-sm">3 Inbound Replies Awaiting Quotation Drafting</div>
                    <div className="text-xs text-dark-muted">Prospects classified as REQUESTING_QUOTE from Aarti & Deepak Nitrite</div>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-dark-muted" />
              </div>

              <div
                onClick={() => navigate("/calibration")}
                className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3.5 transition hover:border-brand-primary hover:bg-dark-hover"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-cyan/15 text-brand-cyan border border-brand-cyan/30">
                    <Gauge className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="font-medium text-white text-sm">5 Customer Assets Due for Calibration within 30 Days</div>
                    <div className="text-xs text-dark-muted">High-pressure transmitters and thermal probes in active buying window</div>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-dark-muted" />
              </div>

              <div
                onClick={() => navigate("/quotations")}
                className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3.5 transition hover:border-brand-primary hover:bg-dark-hover"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-secondary/15 text-brand-secondary border border-brand-secondary/30">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="font-medium text-white text-sm">2 Quotations Pending Version Approval & Send</div>
                    <div className="text-xs text-dark-muted">Auto-generated draft quotations ready for commercial signoff</div>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-dark-muted" />
              </div>
            </div>
          </div>

          {/* Active Opportunities Snapshot */}
          <div className="dark-card p-5">
            <div className="flex items-center justify-between pb-3 border-b border-dark-border">
              <h2 className="font-semibold text-white text-base">High-Value Opportunities</h2>
              <button
                onClick={() => navigate("/pipeline")}
                className="text-xs text-brand-cyan hover:underline flex items-center gap-1"
              >
                <span>View All</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
            </div>

            <div className="mt-4 space-y-2.5">
              {opportunities.length > 0 ? (
                opportunities.map((opp) => (
                  <div
                    key={opp.id}
                    onClick={() => opp.company_id && onOpenCompany(opp.company_id)}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 transition hover:bg-dark-hover"
                  >
                    <div>
                      <div className="font-medium text-white text-sm">{opp.name}</div>
                      <div className="text-xs text-dark-muted flex items-center gap-2">
                        <span className="text-brand-cyan capitalize">{opp.stage}</span>
                        <span>•</span>
                        <span>{opp.probability}% Win Prob</span>
                      </div>
                    </div>
                    <div className="font-mono text-sm font-bold text-white">
                      ₹{Number(opp.estimated_value || 0).toLocaleString("en-IN")}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-6 text-xs text-dark-muted">
                  No active opportunities. Convert from inbound replies or lead factory.
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Sales Radar & Urgent Calibration Windows (5 cols) */}
        <div className="space-y-6 lg:col-span-5">
          {/* Urgent Calibration Renewals Radar */}
          <div className="dark-card p-5">
            <div className="flex items-center justify-between pb-3 border-b border-dark-border">
              <div className="flex items-center gap-2">
                <Gauge className="h-5 w-5 text-brand-cyan" />
                <h2 className="font-semibold text-white text-base">Calibration Radar</h2>
              </div>
              <button
                onClick={() => navigate("/calibration")}
                className="text-xs text-brand-cyan hover:underline"
              >
                Full Asset Board
              </button>
            </div>

            <div className="mt-4 space-y-2.5">
              {calibrationsDue.length > 0 ? (
                calibrationsDue.map((item) => (
                  <div
                    key={item.asset_id || item.id}
                    onClick={() => item.company_id && onOpenCompany(item.company_id)}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 transition hover:bg-dark-hover"
                  >
                    <div>
                      <div className="font-medium text-white text-xs">{item.instrument_name}</div>
                      <div className="text-[11px] text-dark-muted">{item.company_name} • {item.parameter}</div>
                    </div>
                    <div className="text-right">
                      <span className="rounded bg-brand-amber/15 px-2 py-0.5 text-[10px] font-mono font-semibold text-brand-amber border border-brand-amber/30">
                        {item.days_until_due != null ? `${item.days_until_due}d left` : "Due Soon"}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-xl border border-dark-border bg-dark-panel p-4 text-center text-xs text-dark-muted">
                  All active customer instruments calibrated.
                </div>
              )}
            </div>
          </div>

          {/* Territory Cluster Snapshot */}
          <div className="dark-card p-5">
            <div className="flex items-center justify-between pb-3 border-b border-dark-border">
              <div className="flex items-center gap-2">
                <Calendar className="h-5 w-5 text-brand-emerald" />
                <h2 className="font-semibold text-white text-base">Suggested Trip Itinerary</h2>
              </div>
              <button
                onClick={() => navigate("/territory")}
                className="text-xs text-brand-cyan hover:underline"
              >
                Plan Routes
              </button>
            </div>

            <div className="mt-4 rounded-xl border border-brand-emerald/30 bg-brand-emerald/5 p-3.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-white text-xs">Dahej PCPIR & Port Belt</span>
                <span className="text-[10px] font-mono text-brand-emerald font-bold">NEXT TUESDAY</span>
              </div>
              <div className="mt-1 text-xs text-dark-muted">
                3 plants with 8 overdue pressure & thermal instruments within 15 km.
              </div>
              <div className="mt-3 flex items-center justify-between pt-2 border-t border-dark-border text-xs">
                <span className="text-dark-muted">Est. Spend Opportunity:</span>
                <span className="font-mono font-bold text-white">₹38,500</span>
              </div>
            </div>
          </div>

          {/* Inbound Reply Alerts */}
          <div className="dark-card p-5">
            <div className="flex items-center justify-between pb-3 border-b border-dark-border">
              <h2 className="font-semibold text-white text-base">Recent Inbound Replies</h2>
              <button
                onClick={() => navigate("/inbox")}
                className="text-xs text-brand-cyan hover:underline"
              >
                Open Inbox
              </button>
            </div>

            <div className="mt-4 space-y-2.5">
              {recentReplies.length > 0 ? (
                recentReplies.map((rep, idx) => (
                  <div
                    key={idx}
                    onClick={() => rep.company_id && onOpenCompany(rep.company_id)}
                    className="flex cursor-pointer items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 transition hover:bg-dark-hover"
                  >
                    <div>
                      <div className="font-medium text-white text-xs">{rep.company_name || rep.from_email}</div>
                      <div className="text-[11px] text-dark-muted truncate max-w-[200px]">{rep.subject}</div>
                    </div>
                    <span className="rounded bg-brand-primary/20 px-2 py-0.5 text-[10px] font-semibold text-brand-primary border border-brand-primary/30">
                      {rep.classification?.category || "INTERESTED"}
                    </span>
                  </div>
                ))
              ) : (
                <div className="text-center py-4 text-xs text-dark-muted">
                  No new unread replies. Outbound sequences active.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
