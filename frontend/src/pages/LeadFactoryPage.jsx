import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Users,
  Search,
  Filter,
  Flame,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Mail,
  Send,
  Building,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  Plus,
  ArrowRight,
  ExternalLink,
  Zap,
  Globe,
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Info,
  Layers,
  FileText,
  UserCheck,
  UserX,
  Lock,
} from "lucide-react";
import {
  searchApolloLeads,
  getCompanies,
  validateEmail,
  qualifyLead,
  setQualificationStatus,
  discoverAutonomousCalibrationOpportunities,
  executeApolloPilot,
  discoverDecisionMakers,
  getDecisionMakers,
  verifyDecisionMaker,
  enrichDecisionMaker,
  getDecisionMakerResearchBrief,
} from "../api";

const PAN_INDIA_REGIONS = [
  "PAN INDIA",
  "Maharashtra",
  "Tamil Nadu",
  "Karnataka",
  "Telangana",
  "Gujarat",
  "Delhi NCR",
  "Rajasthan",
  "Uttar Pradesh",
  "Madhya Pradesh",
  "West Bengal",
];

const VERIFICATION_STATUS_CONFIG = {
  PERSONA_INFERRED: { label: "Persona Inferred", bg: "bg-blue-500/15", text: "text-blue-400", border: "border-blue-500/30" },
  PERSON_CANDIDATE: { label: "Candidate Found", bg: "bg-amber-500/15", text: "text-amber-400", border: "border-amber-500/30" },
  PERSON_PUBLICLY_VERIFIED: { label: "Publicly Verified", bg: "bg-emerald-500/15", text: "text-emerald-400", border: "border-emerald-500/30" },
  CONTACT_ENRICHMENT_READY: { label: "Enrichment Ready", bg: "bg-indigo-500/15", text: "text-indigo-400", border: "border-indigo-500/30" },
  APOLLO_ENRICHED: { label: "Apollo Enriched", bg: "bg-cyan-500/15", text: "text-cyan-400", border: "border-cyan-500/30" },
  EMAIL_VERIFIED: { label: "Email Verified", bg: "bg-teal-500/15", text: "text-teal-400", border: "border-teal-500/30" },
  PERSON_REJECTED: { label: "Rejected", bg: "bg-rose-500/15", text: "text-rose-400", border: "border-rose-500/30" },
};

const EMAIL_STATUS_CONFIG = {
  NOT_FOUND: { label: "No Email", bg: "bg-dark-bg", text: "text-dark-muted" },
  EMAIL_FOUND: { label: "Email Found", bg: "bg-blue-500/15", text: "text-blue-400" },
  EMAIL_VALIDATED: { label: "RFC Validated", bg: "bg-indigo-500/15", text: "text-indigo-400" },
  EMAIL_VERIFIED: { label: "Deliverable", bg: "bg-emerald-500/15", text: "text-emerald-400" },
  EMAIL_BOUNCE_RISK: { label: "Bounce Risk", bg: "bg-amber-500/15", text: "text-amber-400" },
  EMAIL_SUPPRESSED: { label: "Suppressed", bg: "bg-rose-500/15", text: "text-rose-400" },
};

export default function LeadFactoryPage() {
  const { onOpenCompany } = useOutletContext();

  const [activeTab, setActiveTab] = useState("autonomous"); // autonomous, apollo, database
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRegion, setSelectedRegion] = useState("PAN INDIA");
  const [industryFilter, setIndustryFilter] = useState("all");
  const [discoveredLeads, setDiscoveredLeads] = useState([]);
  const [apolloLeads, setApolloLeads] = useState([]);
  const [dbLeads, setDbLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [validatingEmail, setValidatingEmail] = useState(null);
  const [qualifyingId, setQualifyingId] = useState(null);
  const [discoveringDmId, setDiscoveringDmId] = useState(null);
  const [enrichingCandidateId, setEnrichingCandidateId] = useState(null);
  const [notification, setNotification] = useState("");

  // Decision-maker candidate store per company_id: { [companyId]: { candidates: [], loading: false, brief: null, expanded: false } }
  const [dmStore, setDmStore] = useState({});

  // Active Research Brief modal state
  const [briefModal, setBriefModal] = useState({ open: false, data: null, loading: false });

  // Rejection modal state
  const [rejectModal, setRejectModal] = useState({ open: false, candidateId: null, companyId: null, reason: "company_mismatch", notes: "" });

  const handleRunAutonomousDiscovery = async () => {
    setLoading(true);
    setNotification("");
    try {
      const res = await discoverAutonomousCalibrationOpportunities({
        geography: selectedRegion,
        industry_filter: industryFilter === "all" ? undefined : industryFilter,
        limit: 15,
      });
      setDiscoveredLeads(res.data?.candidates || []);
      setNotification(`Discovered ${res.data?.total_discovered || 0} candidate calibration opportunities across ${selectedRegion}!`);
    } catch (err) {
      console.error("Discovery error:", err);
      setNotification("Failed to run autonomous discovery.");
    } finally {
      setLoading(false);
    }
  };

  const loadManualLeads = async () => {
    setLoading(true);
    try {
      if (activeTab === "apollo") {
        const res = await searchApolloLeads({
          query: searchQuery || "Manufacturing",
          page: 1,
          per_page: 10,
        });
        setApolloLeads(res.data?.results || []);
      } else if (activeTab === "database") {
        const res = await getCompanies({ q: searchQuery, limit: 30 });
        setDbLeads(res.data?.results || res.data || []);
      }
    } catch (err) {
      console.error("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "autonomous") {
      handleRunAutonomousDiscovery();
    } else {
      loadManualLeads();
    }
  }, [activeTab, selectedRegion]);

  // Execute full 8-step decision-maker discovery pipeline
  const handleDiscoverDecisionMakers = async (companyId) => {
    setDiscoveringDmId(companyId);
    setDmStore((prev) => ({
      ...prev,
      [companyId]: { ...prev[companyId], loading: true, expanded: true },
    }));

    try {
      const res = await discoverDecisionMakers(companyId, { trigger_enrichment: false });
      const candidates = res.data?.candidates || [];
      const primary = res.data?.primary_decision_maker;

      setDmStore((prev) => ({
        ...prev,
        [companyId]: {
          candidates,
          primary,
          summary: res.data?.summary || {},
          loading: false,
          expanded: true,
        },
      }));

      const verifiedCount = candidates.filter((c) => c.verification_status === "PERSON_PUBLICLY_VERIFIED" || c.verification_status === "APOLLO_ENRICHED").length;
      setNotification(
        `Decision-Maker Pipeline: Found ${candidates.length} candidates (${verifiedCount} publicly verified) for #${companyId}.`
      );
    } catch (err) {
      console.error("Decision-maker discovery error:", err);
      setNotification("Decision-maker discovery failed for this account.");
      setDmStore((prev) => ({
        ...prev,
        [companyId]: { ...prev[companyId], loading: false },
      }));
    } finally {
      setDiscoveringDmId(null);
    }
  };

  // Load existing decision-makers for an account
  const handleToggleCandidates = async (companyId) => {
    const current = dmStore[companyId];
    if (current?.candidates?.length) {
      setDmStore((prev) => ({
        ...prev,
        [companyId]: { ...prev[companyId], expanded: !prev[companyId].expanded },
      }));
      return;
    }

    setDmStore((prev) => ({
      ...prev,
      [companyId]: { ...prev[companyId], loading: true, expanded: true },
    }));

    try {
      const res = await getDecisionMakers(companyId);
      setDmStore((prev) => ({
        ...prev,
        [companyId]: {
          candidates: res.data?.candidates || [],
          primary: res.data?.primary_decision_maker,
          summary: res.data?.summary || {},
          loading: false,
          expanded: true,
        },
      }));
    } catch (err) {
      setDmStore((prev) => ({
        ...prev,
        [companyId]: { ...prev[companyId], loading: false, expanded: true, candidates: [] },
      }));
    }
  };

  // Apollo single-contact enrichment strictly for verified person
  const handleEnrichSingleCandidate = async (candidateId, companyId) => {
    setEnrichingCandidateId(candidateId);
    try {
      const res = await enrichDecisionMaker(candidateId);
      const updated = res.data?.candidate;
      setNotification(`Apollo Enrichment: ${res.data?.apollo_status} (${updated?.apollo_email || "No direct email"})`);

      // Refresh DM store for this company
      const refreshed = await getDecisionMakers(companyId);
      setDmStore((prev) => ({
        ...prev,
        [companyId]: {
          ...prev[companyId],
          candidates: refreshed.data?.candidates || [],
          primary: refreshed.data?.primary_decision_maker,
        },
      }));
    } catch (err) {
      setNotification("Apollo enrichment failed or safety limit reached.");
    } finally {
      setEnrichingCandidateId(null);
    }
  };

  // Manual verify candidate
  const handleVerifyCandidate = async (candidateId, companyId) => {
    try {
      await verifyDecisionMaker(candidateId, { approved: true });
      setNotification("Candidate manually verified and approved for outreach.");
      const refreshed = await getDecisionMakers(companyId);
      setDmStore((prev) => ({
        ...prev,
        [companyId]: {
          ...prev[companyId],
          candidates: refreshed.data?.candidates || [],
          primary: refreshed.data?.primary_decision_maker,
        },
      }));
    } catch (err) {
      setNotification("Failed to verify candidate.");
    }
  };

  // Manual reject candidate
  const handleOpenRejectModal = (candidateId, companyId) => {
    setRejectModal({
      open: true,
      candidateId,
      companyId,
      reason: "company_mismatch",
      notes: "",
    });
  };

  const handleConfirmReject = async () => {
    if (!rejectModal.candidateId) return;
    try {
      await verifyDecisionMaker(rejectModal.candidateId, {
        approved: false,
        rejection_reason: rejectModal.reason,
        rejection_details: rejectModal.notes,
      });
      setNotification(`Candidate rejected: ${rejectModal.reason}`);
      setRejectModal({ open: false, candidateId: null, companyId: null, reason: "company_mismatch", notes: "" });

      if (rejectModal.companyId) {
        const refreshed = await getDecisionMakers(rejectModal.companyId);
        setDmStore((prev) => ({
          ...prev,
          [rejectModal.companyId]: {
            ...prev[rejectModal.companyId],
            candidates: refreshed.data?.candidates || [],
            primary: refreshed.data?.primary_decision_maker,
          },
        }));
      }
    } catch (err) {
      setNotification("Failed to reject candidate.");
    }
  };

  // Open 24-field Research Brief modal
  const handleOpenResearchBrief = async (companyId) => {
    setBriefModal({ open: true, data: null, loading: true });
    try {
      const res = await getDecisionMakerResearchBrief(companyId);
      setBriefModal({ open: true, data: res.data, loading: false });
    } catch (err) {
      setBriefModal({ open: true, data: null, loading: false });
      setNotification("Failed to load Research Brief.");
    }
  };

  const handleValidateEmail = async (email, index) => {
    if (!email) return;
    setValidatingEmail(index);
    try {
      const res = await validateEmail(email);
      setNotification(`Email ${email}: ${res.data?.status?.toUpperCase()} (${res.data?.reason || "RFC 5322 Valid"})`);
    } catch (err) {
      setNotification(`Validation failed for ${email}`);
    } finally {
      setValidatingEmail(null);
    }
  };

  const handleQualifyLead = async (companyId) => {
    if (!companyId) return;
    setQualifyingId(companyId);
    try {
      const res = await qualifyLead(companyId);
      setNotification(`Lead #${companyId} Qualified: ${res.data?.qualification_status}`);
      if (activeTab === "autonomous") handleRunAutonomousDiscovery();
      else loadManualLeads();
    } catch (err) {
      setNotification("Qualification failed");
    } finally {
      setQualifyingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">Lead Factory & Demand Discovery</h1>
            <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
              PAN-INDIA OPERATING MODEL
            </span>
          </div>
          <p className="text-sm text-dark-muted">
            Person-First Decision-Maker Discovery: Persona Inference → Public Web Evidence → Multi-Factor Verification → Apollo Enrichment → Email.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => (activeTab === "autonomous" ? handleRunAutonomousDiscovery() : loadManualLeads())}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white transition hover:bg-dark-hover disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleRunAutonomousDiscovery}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow transition"
          >
            <Zap className="h-3.5 w-3.5" />
            <span>Discover Calibration Demand</span>
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div className="rounded-xl border border-brand-cyan/30 bg-brand-cyan/10 px-4 py-3 text-xs text-brand-cyan flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Filter & Subnav Bar */}
      <div className="dark-card p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("autonomous")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                activeTab === "autonomous"
                  ? "bg-brand-primary text-white shadow-md shadow-brand-primary/20"
                  : "bg-dark-bg text-dark-muted hover:text-white border border-dark-border"
              }`}
            >
              <Sparkles className="h-3.5 w-3.5 text-brand-cyan" />
              <span>Autonomous Trigger Discovery ({discoveredLeads.length})</span>
            </button>

            <button
              onClick={() => setActiveTab("apollo")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                activeTab === "apollo"
                  ? "bg-brand-primary text-white shadow-md shadow-brand-primary/20"
                  : "bg-dark-bg text-dark-muted hover:text-white border border-dark-border"
              }`}
            >
              <span>Apollo Direct Search</span>
            </button>

            <button
              onClick={() => setActiveTab("database")}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                activeTab === "database"
                  ? "bg-brand-primary text-white shadow-md shadow-brand-primary/20"
                  : "bg-dark-bg text-dark-muted hover:text-white border border-dark-border"
              }`}
            >
              <span>Indexed CRM Accounts</span>
            </button>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-dark-muted">
              <Globe className="h-3.5 w-3.5 text-brand-cyan" />
              <span>Region:</span>
              <select
                value={selectedRegion}
                onChange={(e) => setSelectedRegion(e.target.value)}
                className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-white font-medium"
              >
                {PAN_INDIA_REGIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <select
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-xs text-white"
            >
              <option value="all">All Industries</option>
              <option value="automotive">Automotive</option>
              <option value="aerospace">Aerospace & Defence</option>
              <option value="chemical">Specialty Chemicals</option>
              <option value="electronics">Electronics</option>
              <option value="heavy_engineering">Heavy Engineering</option>
              <option value="pharma">Pharma & Healthcare</option>
            </select>
          </div>
        </div>
      </div>

      {/* TAB 1: AUTONOMOUS TRIGGER DISCOVERY WITH DECISION-MAKER PIPELINE */}
      {activeTab === "autonomous" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4">
            {discoveredLeads.length === 0 ? (
              <div className="dark-card p-12 text-center text-xs text-dark-muted">
                No active trigger signals found for {selectedRegion}. Click "Discover Calibration Demand" to scan configured sources.
              </div>
            ) : (
              discoveredLeads.map((cand) => {
                const compDm = dmStore[cand.company_id] || {};
                const candidates = compDm.candidates || [];
                const isExpanded = compDm.expanded || false;

                return (
                  <div
                    key={cand.company_id}
                    className="dark-card p-5 space-y-4 hover:border-brand-primary/40 transition border border-dark-border"
                  >
                    {/* Top Row: Company & Signal */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-dark-border pb-3">
                      <div>
                        <div className="flex items-center gap-2.5 flex-wrap">
                          <span
                            className="text-base font-bold text-white hover:text-brand-cyan cursor-pointer transition"
                            onClick={() => onOpenCompany(cand.company_id)}
                          >
                            {cand.company_name}
                          </span>
                          <span className="rounded bg-brand-primary/15 px-2 py-0.5 text-[10px] font-mono text-brand-cyan border border-brand-cyan/30">
                            {cand.city}, {cand.state}
                          </span>
                          <span className="rounded bg-dark-bg px-2 py-0.5 text-[10px] text-dark-muted border border-dark-border">
                            {cand.industry}
                          </span>
                        </div>
                        <div className="text-xs text-brand-amber font-medium mt-1 flex items-center gap-1.5">
                          <Zap className="h-3.5 w-3.5 shrink-0" />
                          <span>{cand.event_title}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5 flex-wrap">
                        <div className="text-right mr-1">
                          <div className="font-mono text-lg font-bold text-brand-emerald">{cand.icp_score}</div>
                          <div className="text-[10px] text-dark-muted uppercase font-mono">ICP Score</div>
                        </div>

                        {/* Discover Decision Makers Button */}
                        <button
                          onClick={() => handleDiscoverDecisionMakers(cand.company_id)}
                          disabled={discoveringDmId === cand.company_id}
                          className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-2 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50 transition"
                        >
                          <Users className={`h-3.5 w-3.5 ${discoveringDmId === cand.company_id ? "animate-spin" : ""}`} />
                          <span>{discoveringDmId === cand.company_id ? "Discovering..." : "Discover Decision-Makers"}</span>
                        </button>

                        {/* Research Brief Button */}
                        <button
                          onClick={() => handleOpenResearchBrief(cand.company_id)}
                          className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-2.5 py-2 text-xs text-white hover:bg-dark-hover transition"
                          title="Open 24-Field Research Brief"
                        >
                          <FileText className="h-3.5 w-3.5 text-brand-cyan" />
                          <span>Brief</span>
                        </button>

                        {/* Qualify Button */}
                        <button
                          onClick={() => handleQualifyLead(cand.company_id)}
                          disabled={qualifyingId === cand.company_id}
                          className="flex items-center gap-1.5 rounded-lg border border-brand-emerald/40 bg-brand-emerald/10 px-3 py-2 text-xs font-semibold text-brand-emerald hover:bg-brand-emerald/20 transition"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          <span>Qualify</span>
                        </button>

                        {/* Expand/Collapse Toggle */}
                        <button
                          onClick={() => handleToggleCandidates(cand.company_id)}
                          className="rounded-lg border border-dark-border bg-dark-panel p-2 text-dark-muted hover:text-white transition"
                          title="Toggle Decision-Maker Candidate List"
                        >
                          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>

                    {/* Second-Order Causal Reasoning Chain */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-dark-panel p-3.5 rounded-xl border border-dark-border text-xs">
                      <div>
                        <span className="text-dark-muted font-medium block mb-0.5">1. Business & Plant Change</span>
                        <span className="text-white/90">{cand.causality_chain?.business_change}</span>
                      </div>

                      <div>
                        <span className="text-dark-muted font-medium block mb-0.5">2. Calibration Requirement</span>
                        <span className="text-white/90">{cand.causality_chain?.calibration_impact}</span>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {cand.causality_chain?.likely_parameters?.map((p, idx) => (
                            <span key={idx} className="rounded bg-brand-cyan/15 px-1.5 py-0.5 text-[10px] font-mono text-brand-cyan border border-brand-cyan/30">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div>
                        <span className="text-dark-muted font-medium block mb-0.5">3. Target Stakeholder Persona</span>
                        <span className="text-white/90 font-medium text-brand-amber">{cand.causality_chain?.recommended_role}</span>
                        <p className="text-[11px] text-dark-muted mt-0.5">{cand.causality_chain?.action_strategy}</p>
                      </div>
                    </div>

                    {/* Decision-Maker Discovery Candidates Section */}
                    {isExpanded && (
                      <div className="space-y-3 pt-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Users className="h-4 w-4 text-brand-cyan" />
                            <span className="text-xs font-bold uppercase tracking-wider text-white">
                              Identified Decision-Maker Candidates ({candidates.length})
                            </span>
                          </div>
                          <span className="text-[10px] text-dark-muted">
                            Canonical Flow: Persona → Search → Candidate → Verification → Apollo → Email
                          </span>
                        </div>

                        {compDm.loading ? (
                          <div className="rounded-xl border border-dark-border bg-dark-panel p-6 text-center text-xs text-dark-muted">
                            <RefreshCw className="h-4 w-4 animate-spin mx-auto mb-2 text-brand-primary" />
                            <span>Running live web research and multi-factor person verification...</span>
                          </div>
                        ) : candidates.length === 0 ? (
                          <div className="rounded-xl border border-dark-border bg-dark-panel p-4 text-center text-xs text-dark-muted">
                            No candidates discovered yet for this account. Click "Discover Decision-Makers" above to run the 8-step pipeline.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {candidates.map((c) => {
                              const statusCfg = VERIFICATION_STATUS_CONFIG[c.verification_status] || {
                                label: c.verification_status,
                                bg: "bg-dark-bg",
                                text: "text-dark-muted",
                                border: "border-dark-border",
                              };
                              const emailCfg = EMAIL_STATUS_CONFIG[c.email_status] || EMAIL_STATUS_CONFIG.NOT_FOUND;
                              const isVerified = c.verification_status === "PERSON_PUBLICLY_VERIFIED" || c.verification_status === "APOLLO_ENRICHED" || c.verification_status === "EMAIL_VERIFIED";
                              const isRejected = c.verification_status === "PERSON_REJECTED";

                              return (
                                <div
                                  key={c.id}
                                  className={`rounded-xl border p-4 text-xs transition ${
                                    c.contact_priority === "PRIMARY"
                                      ? "border-brand-primary/50 bg-gradient-to-r from-brand-primary/10 via-dark-panel to-dark-panel"
                                      : "border-dark-border bg-dark-panel"
                                  }`}
                                >
                                  {/* Candidate Header */}
                                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-dark-border/60">
                                    <div>
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <span className="font-bold text-sm text-white">
                                          {c.candidate_name || "Name Unresolved"}
                                        </span>
                                        {c.contact_priority === "PRIMARY" && (
                                          <span className="rounded bg-brand-primary/20 text-brand-cyan border border-brand-cyan/40 px-2 py-0.5 text-[10px] font-mono font-bold">
                                            PRIMARY DECISION-MAKER
                                          </span>
                                        )}
                                        {c.contact_priority === "SECONDARY" && (
                                          <span className="rounded bg-dark-bg text-dark-muted border border-dark-border px-2 py-0.5 text-[10px] font-mono">
                                            SECONDARY
                                          </span>
                                        )}
                                        <span className={`rounded px-2 py-0.5 text-[10px] font-medium border ${statusCfg.bg} ${statusCfg.text} ${statusCfg.border}`}>
                                          {statusCfg.label}
                                        </span>
                                        {c.email_status && (
                                          <span className={`rounded px-2 py-0.5 text-[10px] font-mono ${emailCfg.bg} ${emailCfg.text}`}>
                                            {emailCfg.label}
                                          </span>
                                        )}
                                      </div>
                                      <div className="text-dark-muted mt-0.5">
                                        <span className="text-white font-medium">{c.candidate_title || c.target_persona}</span>
                                        {c.candidate_location && <span> • {c.candidate_location}</span>}
                                        <span className="text-brand-amber font-mono text-[11px] ml-2">[{c.stakeholder_role || "Evaluator"}]</span>
                                      </div>
                                      {c.priority_reason && (
                                        <div className="text-[11px] text-brand-cyan/80 mt-1 italic">
                                          💡 {c.priority_reason}
                                        </div>
                                      )}
                                    </div>

                                    {/* Action Buttons */}
                                    <div className="flex items-center gap-2 flex-wrap">
                                      {/* Apollo Enrichment Button */}
                                      <button
                                        onClick={() => handleEnrichSingleCandidate(c.id, cand.company_id)}
                                        disabled={enrichingCandidateId === c.id || !isVerified}
                                        className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
                                          isVerified
                                            ? "bg-cyan-600 hover:bg-cyan-500 text-white shadow"
                                            : "bg-dark-bg text-dark-muted border border-dark-border cursor-not-allowed opacity-60"
                                        }`}
                                        title={isVerified ? "Enrich verified contact via Apollo (Safety limit: 6 max)" : "Verification required prior to Apollo enrichment"}
                                      >
                                        <Mail className={`h-3 w-3 ${enrichingCandidateId === c.id ? "animate-spin" : ""}`} />
                                        <span>{enrichingCandidateId === c.id ? "Enriching..." : c.apollo_email ? "Re-enrich" : "Apollo Enrich"}</span>
                                      </button>

                                      {/* Manual Operator Verify */}
                                      {!isVerified && !isRejected && (
                                        <button
                                          onClick={() => handleVerifyCandidate(c.id, cand.company_id)}
                                          className="flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition"
                                          title="Manually verify candidate"
                                        >
                                          <UserCheck className="h-3 w-3" />
                                          <span>Verify</span>
                                        </button>
                                      )}

                                      {/* Manual Operator Reject */}
                                      {!isRejected && (
                                        <button
                                          onClick={() => handleOpenRejectModal(c.id, cand.company_id)}
                                          className="flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-400 hover:bg-rose-500/20 transition"
                                          title="Reject candidate with reason"
                                        >
                                          <UserX className="h-3 w-3" />
                                          <span>Reject</span>
                                        </button>
                                      )}
                                    </div>
                                  </div>

                                  {/* Transparent 5-Dimension Verification Match Score Breakdown */}
                                  <div className="mt-3 space-y-1.5 bg-dark-bg/60 p-3 rounded-lg border border-dark-border/40">
                                    <div className="flex items-center justify-between text-[11px]">
                                      <span className="font-semibold text-white">Verification Match Score:</span>
                                      <span className="font-mono font-bold text-brand-emerald">
                                        {((c.score_composite || 0) * 100).toFixed(0)}% ({(c.score_composite || 0).toFixed(2)} / 1.00)
                                      </span>
                                    </div>

                                    {/* 5-Dimension Visual Progress Bars */}
                                    <div className="grid grid-cols-5 gap-2 pt-1">
                                      <div>
                                        <div className="flex justify-between text-[9px] text-dark-muted font-mono mb-0.5">
                                          <span>Company (30%)</span>
                                          <span>{((c.score_company_match || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-dark-panel rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-blue-500 rounded-full"
                                            style={{ width: `${Math.min(100, (c.score_company_match || 0) * 100)}%` }}
                                          />
                                        </div>
                                      </div>

                                      <div>
                                        <div className="flex justify-between text-[9px] text-dark-muted font-mono mb-0.5">
                                          <span>Role (30%)</span>
                                          <span>{((c.score_role_relevance || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-dark-panel rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-indigo-500 rounded-full"
                                            style={{ width: `${Math.min(100, (c.score_role_relevance || 0) * 100)}%` }}
                                          />
                                        </div>
                                      </div>

                                      <div>
                                        <div className="flex justify-between text-[9px] text-dark-muted font-mono mb-0.5">
                                          <span>Facility (10%)</span>
                                          <span>{((c.score_facility_match || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-dark-panel rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-cyan-500 rounded-full"
                                            style={{ width: `${Math.min(100, (c.score_facility_match || 0) * 100)}%` }}
                                          />
                                        </div>
                                      </div>

                                      <div>
                                        <div className="flex justify-between text-[9px] text-dark-muted font-mono mb-0.5">
                                          <span>Recency (15%)</span>
                                          <span>{((c.score_recency || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-dark-panel rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-amber-500 rounded-full"
                                            style={{ width: `${Math.min(100, (c.score_recency || 0) * 100)}%` }}
                                          />
                                        </div>
                                      </div>

                                      <div>
                                        <div className="flex justify-between text-[9px] text-dark-muted font-mono mb-0.5">
                                          <span>Evidence (15%)</span>
                                          <span>{((c.score_evidence_quality || 0) * 100).toFixed(0)}%</span>
                                        </div>
                                        <div className="h-1.5 bg-dark-panel rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-teal-500 rounded-full"
                                            style={{ width: `${Math.min(100, (c.score_evidence_quality || 0) * 100)}%` }}
                                          />
                                        </div>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Evidence Trail & Apollo Results */}
                                  <div className="mt-2.5 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                                    {/* Evidence Trail */}
                                    <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                                      <span className="text-dark-muted font-medium block mb-1">Public Evidence Snippet:</span>
                                      <p className="text-white/80 line-clamp-2">
                                        {c.public_profile_evidence || (c.evidence_sources?.[0]?.snippet) || "Public search record verified against corporate registry / directory."}
                                      </p>
                                      {c.public_profile_url && (
                                        <a
                                          href={c.public_profile_url}
                                          target="_blank"
                                          rel="noreferrer"
                                          className="text-brand-cyan hover:underline inline-flex items-center gap-1 mt-1 text-[10px]"
                                        >
                                          <span>{c.public_profile_url.slice(0, 45)}...</span>
                                          <ExternalLink className="h-2.5 w-2.5" />
                                        </a>
                                      )}
                                    </div>

                                    {/* Apollo / Email Status */}
                                    <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                                      <span className="text-dark-muted font-medium block mb-1">Contact Intelligence:</span>
                                      {c.apollo_email ? (
                                        <div className="space-y-0.5">
                                          <div className="font-mono text-brand-emerald font-semibold">{c.apollo_email}</div>
                                          <div className="text-[10px] text-dark-muted">
                                            Status: <span className="text-white">{c.email_status}</span> • Phone: {c.apollo_phone || "Not Listed"}
                                          </div>
                                        </div>
                                      ) : c.apollo_enrichment_status === "APOLLO_BLOCKED" ? (
                                        <span className="text-brand-amber">Apollo enrichment unconfigured / blocked (Safety limit).</span>
                                      ) : (
                                        <span className="text-dark-muted">Enrichment pending manual or automated trigger.</span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* TAB 2: APOLLO DIRECT SEARCH */}
      {activeTab === "apollo" && (
        <div className="dark-card p-4 space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-dark-border">
            <span className="text-xs font-semibold text-white">Apollo Enriched Contacts (Safety Limit Enforced: Max 6 per run)</span>
            <span className="text-[10px] font-mono text-brand-amber border border-brand-amber/30 rounded px-2 py-0.5">
              SAFETY GUARD ACTIVE
            </span>
          </div>

          <div className="divide-y divide-dark-border border border-dark-border rounded-xl overflow-hidden">
            {apolloLeads.length === 0 ? (
              <div className="p-8 text-center text-xs text-dark-muted">No Apollo records returned.</div>
            ) : (
              apolloLeads.map((l, idx) => (
                <div key={idx} className="p-3.5 bg-dark-panel flex items-center justify-between text-xs">
                  <div>
                    <div className="font-semibold text-white">{l.name || l.first_name}</div>
                    <div className="text-dark-muted text-[11px]">{l.title} • {l.company_name}</div>
                    <div className="text-brand-cyan font-mono text-[11px] mt-0.5">{l.email}</div>
                  </div>
                  <button
                    onClick={() => handleValidateEmail(l.email, idx)}
                    disabled={validatingEmail === idx}
                    className="rounded border border-dark-border bg-dark-card px-2.5 py-1 text-xs text-dark-muted hover:text-white"
                  >
                    {validatingEmail === idx ? "Checking..." : "Validate RFC 5322"}
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* TAB 3: INDEXED CRM ACCOUNTS */}
      {activeTab === "database" && (
        <div className="dark-card p-4 space-y-3">
          <div className="divide-y divide-dark-border border border-dark-border rounded-xl overflow-hidden">
            {dbLeads.map((c) => (
              <div key={c.id} className="p-3.5 bg-dark-panel flex items-center justify-between text-xs">
                <div>
                  <div className="font-semibold text-white cursor-pointer hover:underline" onClick={() => onOpenCompany(c.id)}>
                    {c.name}
                  </div>
                  <div className="text-dark-muted text-[11px]">{c.city}, {c.state} • {c.industry}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-brand-emerald font-bold">{c.icp_score || 70}</span>
                  <span className="rounded bg-brand-primary/20 text-brand-cyan text-[10px] px-2 py-0.5 font-mono">{c.lead_status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 24-FIELD RESEARCH BRIEF MODAL */}
      {briefModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in">
          <div className="dark-card w-full max-w-3xl max-h-[90vh] flex flex-col border border-brand-primary/40 shadow-2xl overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-dark-border p-4 bg-dark-panel">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-brand-cyan" />
                <h2 className="text-base font-bold text-white">24-Field Account Research & Decision-Maker Brief</h2>
              </div>
              <button
                onClick={() => setBriefModal({ open: false, data: null, loading: false })}
                className="rounded-lg p-1.5 text-dark-muted hover:bg-dark-hover hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
              {briefModal.loading ? (
                <div className="p-12 text-center text-dark-muted">
                  <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-primary" />
                  <span>Assembling 24-field intelligence brief...</span>
                </div>
              ) : briefModal.data ? (
                <div className="space-y-4">
                  {/* Company & Core Intelligence */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-dark-panel p-4 rounded-xl border border-dark-border">
                    <div>
                      <div className="text-[10px] text-dark-muted uppercase font-mono">1. Company Name</div>
                      <div className="text-sm font-bold text-white mt-0.5">{briefModal.data.company_name}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-dark-muted uppercase font-mono">2. Domain</div>
                      <div className="font-mono text-brand-cyan mt-0.5">{briefModal.data.company_domain || "Not Indexed"}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-dark-muted uppercase font-mono">3. Industry</div>
                      <div className="text-white mt-0.5">{briefModal.data.industry}</div>
                    </div>
                    <div>
                      <div className="text-[10px] text-dark-muted uppercase font-mono">4. Primary Facility / State</div>
                      <div className="text-white mt-0.5">{briefModal.data.primary_facility || briefModal.data.plant_locations?.join(", ") || "Pan-India"}</div>
                    </div>
                  </div>

                  {/* Primary Stakeholder Section */}
                  <div className="bg-dark-panel p-4 rounded-xl border border-brand-primary/40 space-y-3">
                    <div className="flex items-center justify-between border-b border-dark-border pb-2">
                      <span className="font-bold text-white text-xs uppercase tracking-wider text-brand-cyan">
                        Primary Decision-Maker Profile
                      </span>
                      <span className="rounded bg-brand-primary/20 text-brand-cyan px-2 py-0.5 text-[10px] font-mono">
                        {briefModal.data.verification_status}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">7. Stakeholder Name</div>
                        <div className="text-sm font-bold text-white mt-0.5">{briefModal.data.primary_stakeholder_name || "Unresolved"}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">8. Designaton / Title</div>
                        <div className="text-white mt-0.5">{briefModal.data.primary_stakeholder_title || briefModal.data.target_persona}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">9. Stakeholder Role</div>
                        <div className="text-brand-amber font-medium mt-0.5">{briefModal.data.stakeholder_role || "Evaluator"}</div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">11. Priority Selection Reason</div>
                        <div className="text-dark-muted italic mt-0.5">{briefModal.data.priority_reason || "Highest composite match score for calibration demand."}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">15. Composite Match Score</div>
                        <div className="font-mono text-sm font-bold text-brand-emerald mt-0.5">
                          {((briefModal.data.composite_match_score || 0) * 100).toFixed(0)}% ({(briefModal.data.composite_match_score || 0).toFixed(2)} / 1.00)
                        </div>
                      </div>
                    </div>

                    {/* Contact details */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-dark-border">
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">20. Primary Email</div>
                        <div className="font-mono text-brand-emerald mt-0.5">{briefModal.data.primary_email || "Not Enriched"}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">21. Email Status</div>
                        <div className="text-white mt-0.5">{briefModal.data.email_status || "NOT_FOUND"}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">22. Phone</div>
                        <div className="text-white mt-0.5">{briefModal.data.primary_phone || "Not Listed"}</div>
                      </div>
                    </div>
                  </div>

                  {/* Outreach Strategy & Trigger Signal */}
                  <div className="bg-dark-panel p-4 rounded-xl border border-dark-border space-y-2">
                    <div>
                      <div className="text-[10px] text-dark-muted uppercase font-mono">23. Trigger Signal Summary</div>
                      <div className="text-white mt-0.5">{briefModal.data.trigger_signal_summary}</div>
                    </div>
                    <div className="pt-2">
                      <div className="text-[10px] text-dark-muted uppercase font-mono">24. Recommended Outreach Angle</div>
                      <div className="text-brand-amber font-medium mt-0.5">{briefModal.data.recommended_outreach_angle}</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-dark-muted">No Research Brief available.</div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="border-t border-dark-border p-3 bg-dark-panel flex justify-end">
              <button
                onClick={() => setBriefModal({ open: false, data: null, loading: false })}
                className="rounded-lg bg-dark-bg border border-dark-border px-4 py-1.5 text-xs text-white hover:bg-dark-hover transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REJECTION REASON MODAL */}
      {rejectModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in">
          <div className="dark-card w-full max-w-md border border-rose-500/40 p-5 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-dark-border pb-2">
              <span className="font-bold text-white text-sm">Reject Decision-Maker Candidate</span>
              <button onClick={() => setRejectModal({ open: false, candidateId: null, companyId: null, reason: "company_mismatch", notes: "" })} className="text-dark-muted hover:text-white">✕</button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Rejection Reason</label>
                <select
                  value={rejectModal.reason}
                  onChange={(e) => setRejectModal((prev) => ({ ...prev, reason: e.target.value }))}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg p-2 text-white"
                >
                  <option value="company_mismatch">Company Mismatch (Not at this company)</option>
                  <option value="outdated_employment">Outdated Employment (Left organization)</option>
                  <option value="irrelevant_role">Irrelevant Role (Non-decision maker)</option>
                  <option value="insufficient_evidence">Insufficient Evidence</option>
                  <option value="duplicate">Duplicate Record</option>
                  <option value="wrong_facility">Wrong Plant / Facility</option>
                  <option value="conflicting_sources">Conflicting Evidence Sources</option>
                </select>
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Operator Notes (Optional)</label>
                <textarea
                  value={rejectModal.notes}
                  onChange={(e) => setRejectModal((prev) => ({ ...prev, notes: e.target.value }))}
                  rows={3}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg p-2 text-white placeholder-dark-muted"
                  placeholder="Explain why this candidate was rejected..."
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setRejectModal({ open: false, candidateId: null, companyId: null, reason: "company_mismatch", notes: "" })}
                className="rounded-lg border border-dark-border bg-dark-bg px-3 py-1.5 text-xs text-dark-muted hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmReject}
                className="rounded-lg bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-rose-500 transition"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

