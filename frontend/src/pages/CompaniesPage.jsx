import React, { useState, useEffect } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import {
  Building,
  Search,
  Filter,
  MapPin,
  Flame,
  Gauge,
  FileText,
  Clock,
  Send,
  ShieldAlert,
  Bot,
  Plus,
  ArrowUpRight,
  ChevronRight,
  ExternalLink,
  Users,
  UserCheck,
  UserX,
  Mail,
  RefreshCw,
  Zap,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import {
  getCompanies,
  getCompany360,
  getCompanyFacilities,
  getCompanyAssets,
  getNextAction,
  getDecisionMakers,
  discoverDecisionMakers,
  verifyDecisionMaker,
  enrichDecisionMaker,
  getDecisionMakerResearchBrief,
} from "../api";

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

export default function CompaniesPage() {
  const { onOpenCompany } = useOutletContext();
  const [searchParams] = useSearchParams();

  const [companies, setCompanies] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [c360, setC360] = useState(null);
  const [facilities, setFacilities] = useState([]);
  const [assets, setAssets] = useState([]);
  const [nextAction, setNextAction] = useState(null);
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Decision-maker discovery state
  const [dmData, setDmData] = useState({ candidates: [], primary: null, summary: null, loading: false });
  const [discoveringDm, setDiscoveringDm] = useState(false);
  const [enrichingCandidateId, setEnrichingCandidateId] = useState(null);
  const [notification, setNotification] = useState("");

  // Research brief modal
  const [briefModal, setBriefModal] = useState({ open: false, data: null, loading: false });

  // Rejection modal
  const [rejectModal, setRejectModal] = useState({ open: false, candidateId: null, reason: "company_mismatch", notes: "" });

  useEffect(() => {
    const loadList = async () => {
      setLoadingList(true);
      try {
        const res = await getCompanies({ limit: 50 });
        const list = res.data?.results || res.data || [];
        setCompanies(list);
        if (list.length > 0) {
          const initialId = searchParams.get("id") ? Number(searchParams.get("id")) : list[0].id;
          setSelectedId(initialId);
        }
      } catch (err) {
        console.error("Failed to load companies:", err);
      } finally {
        setLoadingList(false);
      }
    };
    loadList();
  }, [searchParams]);

  const loadDecisionMakers = async (companyId) => {
    setDmData((prev) => ({ ...prev, loading: true }));
    try {
      const res = await getDecisionMakers(companyId);
      setDmData({
        candidates: res.data?.candidates || [],
        primary: res.data?.primary_decision_maker,
        summary: res.data?.summary,
        loading: false,
      });
    } catch (err) {
      setDmData({ candidates: [], primary: null, summary: null, loading: false });
    }
  };

  useEffect(() => {
    if (!selectedId) return;

    const loadDetail = async () => {
      setLoadingDetail(true);
      try {
        const [c360Res, facRes, astRes, nbaRes] = await Promise.allSettled([
          getCompany360(selectedId),
          getCompanyFacilities(selectedId),
          getCompanyAssets(selectedId),
          getNextAction(selectedId),
        ]);

        if (c360Res.status === "fulfilled") setC360(c360Res.value.data);
        if (facRes.status === "fulfilled") setFacilities(facRes.value.data?.results || facRes.value.data || []);
        if (astRes.status === "fulfilled") setAssets(astRes.value.data?.results || astRes.value.data || []);
        if (nbaRes.status === "fulfilled") setNextAction(nbaRes.value.data);

        loadDecisionMakers(selectedId);
      } catch (err) {
        console.error("Detail load error:", err);
      } finally {
        setLoadingDetail(false);
      }
    };
    loadDetail();
  }, [selectedId]);

  const handleRunDiscoveryPipeline = async () => {
    if (!selectedId) return;
    setDiscoveringDm(true);
    setNotification("");
    try {
      const res = await discoverDecisionMakers(selectedId, { trigger_enrichment: false });
      setDmData({
        candidates: res.data?.candidates || [],
        primary: res.data?.primary_decision_maker,
        summary: res.data?.summary,
        loading: false,
      });
      const verifiedCount = (res.data?.candidates || []).filter((c) => c.verification_status === "PERSON_PUBLICLY_VERIFIED" || c.verification_status === "APOLLO_ENRICHED").length;
      setNotification(`Discovered ${res.data?.candidates?.length || 0} candidates (${verifiedCount} verified) for ${comp?.name}.`);
    } catch (err) {
      setNotification("Failed to run decision-maker discovery pipeline.");
    } finally {
      setDiscoveringDm(false);
    }
  };

  const handleEnrichCandidate = async (candidateId) => {
    setEnrichingCandidateId(candidateId);
    try {
      const res = await enrichDecisionMaker(candidateId);
      const email = res.data?.candidate?.apollo_email;
      setNotification(`Apollo Enrichment: ${res.data?.apollo_status} (${email || "No direct email"})`);
      loadDecisionMakers(selectedId);
    } catch (err) {
      setNotification("Apollo enrichment failed or safety limit reached.");
    } finally {
      setEnrichingCandidateId(null);
    }
  };

  const handleVerifyCandidate = async (candidateId) => {
    try {
      await verifyDecisionMaker(candidateId, { approved: true });
      setNotification("Candidate manually verified.");
      loadDecisionMakers(selectedId);
    } catch (err) {
      setNotification("Failed to verify candidate.");
    }
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
      setRejectModal({ open: false, candidateId: null, reason: "company_mismatch", notes: "" });
      loadDecisionMakers(selectedId);
    } catch (err) {
      setNotification("Failed to reject candidate.");
    }
  };

  const handleOpenResearchBrief = async () => {
    if (!selectedId) return;
    setBriefModal({ open: true, data: null, loading: true });
    try {
      const res = await getDecisionMakerResearchBrief(selectedId);
      setBriefModal({ open: true, data: res.data, loading: false });
    } catch (err) {
      setBriefModal({ open: true, data: null, loading: false });
      setNotification("Failed to load Research Brief.");
    }
  };

  const filteredCompanies = companies.filter(
    (c) =>
      c.name?.toLowerCase().includes(search.toLowerCase()) ||
      c.city?.toLowerCase().includes(search.toLowerCase()) ||
      c.industry?.toLowerCase().includes(search.toLowerCase())
  );

  const comp = c360?.company;

  // Group decision maker candidates by priority
  const primaryCandidate = dmData.candidates.find((c) => c.contact_priority === "PRIMARY");
  const secondaryCandidates = dmData.candidates.filter((c) => c.contact_priority === "SECONDARY");
  const otherCandidates = dmData.candidates.filter((c) => c.contact_priority !== "PRIMARY" && c.contact_priority !== "SECONDARY");

  return (
    <div className="space-y-6">
      {/* Top Notification */}
      {notification && (
        <div className="rounded-xl border border-brand-cyan/30 bg-brand-cyan/10 px-4 py-3 text-xs text-brand-cyan flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Top Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Companies & Account 360</h1>
          <p className="text-sm text-dark-muted">
            Pan-India manufacturing accounts, plant facilities, customer assets, verified decision-makers, and CRM timeline.
          </p>
        </div>
      </div>

      {/* Main Dual-Pane Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Pane: Company List */}
        <div className="space-y-3 lg:col-span-4">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-dark-muted" />
            <input
              type="text"
              placeholder="Search companies, cities, sectors..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl border border-dark-border bg-dark-panel py-2 pl-9 pr-4 text-xs text-white placeholder-dark-muted focus:border-brand-primary focus:outline-none"
            />
          </div>

          <div className="divide-y divide-dark-border overflow-hidden rounded-2xl border border-dark-border bg-dark-panel">
            {loadingList ? (
              <div className="p-8 text-center text-xs text-dark-muted">
                <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-brand-primary" />
                <span>Loading companies...</span>
              </div>
            ) : filteredCompanies.length === 0 ? (
              <div className="p-8 text-center text-xs text-dark-muted">No accounts match search.</div>
            ) : (
              filteredCompanies.map((c) => {
                const isSelected = c.id === selectedId;
                return (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={`flex w-full items-center justify-between p-3.5 text-left transition ${
                      isSelected ? "bg-brand-primary/15 border-l-4 border-brand-primary" : "hover:bg-dark-hover"
                    }`}
                  >
                    <div>
                      <div className="font-semibold text-white text-xs">{c.name}</div>
                      <div className="mt-0.5 text-[11px] text-dark-muted">
                        {c.city || "Pan-India"}{c.state ? `, ${c.state}` : ""} • {c.industry || "Manufacturing"}
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-xs font-bold text-brand-emerald">{Math.round(c.icp_score || 70)}</span>
                      <div className="text-[9px] text-dark-muted uppercase font-mono">ICP</div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Pane: Company 360 Detail */}
        <div className="space-y-4 lg:col-span-8">
          {loadingDetail ? (
            <div className="dark-card p-12 text-center text-xs text-dark-muted">
              <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-primary" />
              <span>Loading Company 360 & Decision-Maker Intelligence...</span>
            </div>
          ) : !comp ? (
            <div className="dark-card p-12 text-center text-xs text-dark-muted">
              Select an account from the list to view Account 360 and verified stakeholders.
            </div>
          ) : (
            <div className="dark-card flex flex-col overflow-hidden">
              {/* Header Box */}
              <div className="border-b border-dark-border p-5 bg-dark-panel">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5 flex-wrap">
                      <h2 className="text-lg font-bold text-white">{comp.name}</h2>
                      <span className="rounded bg-brand-primary/20 px-2 py-0.5 font-mono text-[10px] font-bold text-brand-cyan border border-brand-cyan/40">
                        {comp.city || "Pan-India"}{comp.state ? `, ${comp.state}` : ""}
                      </span>
                      {comp.has_nabl && (
                        <span className="rounded bg-brand-emerald/15 px-2 py-0.5 font-mono text-[10px] text-brand-emerald border border-brand-emerald/30">
                          NABL ACCREDITED
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-dark-muted">
                      <span>{comp.industry || "Manufacturing"}</span>
                      <span>•</span>
                      <span className="font-mono text-brand-cyan">ICP Score: {Math.round(comp.icp_score || 0)}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      onClick={handleRunDiscoveryPipeline}
                      disabled={discoveringDm}
                      className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50 transition"
                    >
                      <Users className={`h-3.5 w-3.5 ${discoveringDm ? "animate-spin" : ""}`} />
                      <span>{discoveringDm ? "Discovering..." : "Discover Decision-Makers"}</span>
                    </button>

                    <button
                      onClick={handleOpenResearchBrief}
                      className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1.5 text-xs text-white hover:bg-dark-hover transition"
                    >
                      <FileText className="h-3.5 w-3.5 text-brand-cyan" />
                      <span>Research Brief</span>
                    </button>
                  </div>
                </div>

                {/* Tabs */}
                <div className="mt-4 flex border-b border-dark-border text-xs font-medium space-x-4 overflow-x-auto">
                  {[
                    { id: "overview", label: "Overview & Signals" },
                    { id: "decision_makers", label: `Decision-Makers & Verification (${dmData.candidates.length})` },
                    { id: "facilities", label: `Facilities (${facilities.length})` },
                    { id: "assets", label: `Customer Assets (${assets.length})` },
                    { id: "pipeline", label: `Pipeline & Quotes (${(c360?.opportunities?.length || 0) + (c360?.quotations?.length || 0)})` },
                    { id: "activities", label: `Activities (${c360?.activities?.length || 0})` },
                    { id: "research", label: "Web Research & Competitors" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setActiveTab(t.id)}
                      className={`pb-2.5 transition-colors whitespace-nowrap ${
                        activeTab === t.id
                          ? "border-b-2 border-brand-primary text-white font-semibold"
                          : "text-dark-muted hover:text-white"
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab Content Area */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {/* TAB: OVERVIEW */}
                {activeTab === "overview" && (
                  <div className="space-y-4">
                    {/* Next Best Action Card */}
                    <div className="rounded-xl border border-brand-primary/40 bg-gradient-to-br from-brand-primary/15 via-dark-panel to-dark-panel p-4 shadow-md">
                      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand-cyan">
                        <Bot className="h-4 w-4" />
                        <span>AI Recommended Next Best Action</span>
                      </div>
                      <div className="mt-2 text-sm font-semibold text-white">
                        {nextAction?.action || comp.urgency_reason || "Schedule on-site calibration audit and scope review"}
                      </div>
                      <div className="mt-1 text-xs text-dark-muted">
                        Timing: <span className="text-brand-amber font-medium">{nextAction?.timing || "Within 48 hours"}</span> • Reason: {nextAction?.reason || "Active calibration buying window"}
                      </div>
                    </div>

                    {/* Key Attributes */}
                    <div className="grid grid-cols-3 gap-3">
                      <div className="dark-card p-3">
                        <div className="text-[11px] text-dark-muted uppercase font-medium">Buying Window</div>
                        <div className="mt-1 text-sm font-bold text-brand-amber capitalize">
                          {(comp.buying_window || "next_30_days").replaceAll("_", " ")}
                        </div>
                      </div>
                      <div className="dark-card p-3">
                        <div className="text-[11px] text-dark-muted uppercase font-medium">Stage</div>
                        <div className="mt-1 text-sm font-bold text-white capitalize">{comp.lead_status}</div>
                      </div>
                      <div className="dark-card p-3">
                        <div className="text-[11px] text-dark-muted uppercase font-medium">Turnaround SLA</div>
                        <div className="mt-1 text-sm font-bold text-brand-emerald">48 Hours</div>
                      </div>
                    </div>

                    {/* Quick Contacts Summary */}
                    <div className="dark-card p-4">
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-semibold uppercase tracking-wider text-dark-muted">
                          Plant & Quality Decision Makers ({dmData.candidates.length || c360?.contacts?.length || 0})
                        </span>
                        <button onClick={() => setActiveTab("decision_makers")} className="text-xs text-brand-cyan hover:underline">
                          View Verification Matrix →
                        </button>
                      </div>
                      <div className="space-y-2">
                        {dmData.candidates.slice(0, 3).map((c) => (
                          <div key={c.id} className="flex items-center justify-between rounded-lg bg-dark-bg p-2.5 text-xs">
                            <div>
                              <div className="font-semibold text-white">{c.candidate_name || "Unresolved"}</div>
                              <div className="text-dark-muted">{c.candidate_title || c.target_persona}</div>
                            </div>
                            <div className="font-mono text-brand-cyan">{c.apollo_email || "Email pending"}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB: DECISION-MAKERS & VERIFICATION */}
                {activeTab === "decision_makers" && (
                  <div className="space-y-4">
                    {/* Top Action & Summary Bar */}
                    <div className="flex items-center justify-between flex-wrap gap-2 bg-dark-panel p-3.5 rounded-xl border border-dark-border">
                      <div>
                        <div className="text-xs font-bold text-white">Decision-Maker Discovery & Multi-Stakeholder Matrix</div>
                        <div className="text-[11px] text-dark-muted">
                          Person-First Discovery: Target Persona → Public Evidence → Verification → Apollo Enrichment → Email
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleRunDiscoveryPipeline}
                          disabled={discoveringDm}
                          className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50 transition"
                        >
                          <RefreshCw className={`h-3.5 w-3.5 ${discoveringDm ? "animate-spin" : ""}`} />
                          <span>Run 8-Step Discovery</span>
                        </button>
                      </div>
                    </div>

                    {dmData.loading ? (
                      <div className="p-12 text-center text-xs text-dark-muted">
                        <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-primary" />
                        <span>Loading decision-makers and verification scores...</span>
                      </div>
                    ) : dmData.candidates.length === 0 ? (
                      <div className="rounded-xl border border-dark-border bg-dark-panel p-8 text-center text-xs text-dark-muted">
                        <Users className="h-8 w-8 mx-auto mb-2 text-dark-muted opacity-40" />
                        <p>No decision-maker candidates discovered for this account yet.</p>
                        <button
                          onClick={handleRunDiscoveryPipeline}
                          disabled={discoveringDm}
                          className="mt-3 rounded-lg bg-brand-primary px-3.5 py-1.5 text-xs font-semibold text-white"
                        >
                          Discover Decision-Makers Now
                        </button>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {/* 1. PRIMARY DECISION-MAKER */}
                        {primaryCandidate && (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-brand-primary/20 text-brand-cyan border border-brand-cyan/40 px-2 py-0.5 text-[10px] font-mono font-bold">
                                PRIMARY DECISION-MAKER
                              </span>
                              <span className="text-xs text-dark-muted">Highest verification match score for this account</span>
                            </div>

                            <CandidateCard
                              c={primaryCandidate}
                              onEnrich={() => handleEnrichCandidate(primaryCandidate.id)}
                              onVerify={() => handleVerifyCandidate(primaryCandidate.id)}
                              onReject={() => setRejectModal({ open: true, candidateId: primaryCandidate.id, reason: "company_mismatch", notes: "" })}
                              enrichingId={enrichingCandidateId}
                              isPrimary
                            />
                          </div>
                        )}

                        {/* 2. SECONDARY STAKEHOLDERS */}
                        {secondaryCandidates.length > 0 && (
                          <div className="space-y-2 pt-2">
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-dark-bg text-dark-muted border border-dark-border px-2 py-0.5 text-[10px] font-mono font-bold">
                                SECONDARY STAKEHOLDERS ({secondaryCandidates.length})
                              </span>
                              <span className="text-xs text-dark-muted">Supporting Evaluators, Recommenders, and Purchasers</span>
                            </div>

                            <div className="space-y-3">
                              {secondaryCandidates.map((c) => (
                                <CandidateCard
                                  key={c.id}
                                  c={c}
                                  onEnrich={() => handleEnrichCandidate(c.id)}
                                  onVerify={() => handleVerifyCandidate(c.id)}
                                  onReject={() => setRejectModal({ open: true, candidateId: c.id, reason: "company_mismatch", notes: "" })}
                                  enrichingId={enrichingCandidateId}
                                />
                              ))}
                            </div>
                          </div>
                        )}

                        {/* 3. OTHER / UNVERIFIED CANDIDATES */}
                        {otherCandidates.length > 0 && (
                          <div className="space-y-2 pt-2">
                            <div className="flex items-center gap-2">
                              <span className="rounded bg-dark-bg text-dark-muted border border-dark-border px-2 py-0.5 text-[10px] font-mono">
                                OTHER / CANDIDATES ({otherCandidates.length})
                              </span>
                            </div>

                            <div className="space-y-3">
                              {otherCandidates.map((c) => (
                                <CandidateCard
                                  key={c.id}
                                  c={c}
                                  onEnrich={() => handleEnrichCandidate(c.id)}
                                  onVerify={() => handleVerifyCandidate(c.id)}
                                  onReject={() => setRejectModal({ open: true, candidateId: c.id, reason: "company_mismatch", notes: "" })}
                                  enrichingId={enrichingCandidateId}
                                />
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* TAB: FACILITIES */}
                {activeTab === "facilities" && (
                  <div className="space-y-3">
                    {facilities.length > 0 ? (
                      facilities.map((fac) => (
                        <div key={fac.id} className="rounded-xl border border-dark-border bg-dark-card p-4">
                          <div className="flex items-center justify-between">
                            <div className="font-semibold text-white text-sm">{fac.name}</div>
                            <span className="rounded bg-brand-primary/10 px-2 py-0.5 text-xs font-mono text-brand-primary">
                              Plant #{fac.id}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-dark-muted">
                            Location: {fac.industrial_estate || fac.city || "Pan-India"} • Headcount: {fac.headcount || "50-200"}
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="p-8 text-center text-xs text-dark-muted">
                        No distinct plant facilities configured.
                      </div>
                    )}
                  </div>
                )}

                {/* TAB: ASSETS */}
                {activeTab === "assets" && (
                  <div className="space-y-2">
                    {assets.length > 0 ? (
                      assets.map((ast) => (
                        <div key={ast.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                          <div>
                            <div className="font-medium text-white text-sm">{ast.instrument_name}</div>
                            <div className="text-dark-muted">
                              {ast.parameter} • {ast.make_model || "Standard"} • Due: <span className="text-brand-amber font-mono font-medium">{ast.calibration_due_date || "Upcoming"}</span>
                            </div>
                          </div>
                          <span className="badge-cyan rounded px-2 py-0.5 text-xs">
                            NABL Covered
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="p-8 text-center text-xs text-dark-muted">
                        No customer assets recorded.
                      </div>
                    )}
                  </div>
                )}

                {/* TAB: PIPELINE */}
                {activeTab === "pipeline" && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold uppercase text-dark-muted mb-2">Opportunities</h3>
                      <div className="space-y-2">
                        {c360?.opportunities?.map((opp) => (
                          <div key={opp.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                            <div>
                              <div className="font-medium text-white text-sm">{opp.name}</div>
                              <div className="text-dark-muted">Stage: {opp.stage} • Probability: {opp.probability}%</div>
                            </div>
                            <div className="font-mono font-bold text-white">
                              ₹{Number(opp.estimated_value || 0).toLocaleString("en-IN")}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h3 className="text-xs font-semibold uppercase text-dark-muted mb-2">Quotations</h3>
                      <div className="space-y-2">
                        {c360?.quotations?.map((q) => (
                          <div key={q.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                            <div>
                              <div className="font-medium text-white text-sm">{q.quotation_number || `Quote #${q.id}`}</div>
                              <div className="text-dark-muted">Version {q.version_number || 1} • Status: {q.status}</div>
                            </div>
                            <div className="font-mono font-bold text-brand-emerald">
                              ₹{Number(q.total || 0).toLocaleString("en-IN")}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* TAB: ACTIVITIES */}
                {activeTab === "activities" && (
                  <div className="space-y-2">
                    {c360?.activities?.length > 0 ? (
                      c360.activities.map((a) => (
                        <div key={a.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-white">{a.activity_type}</span>
                            <span className="text-dark-muted font-mono text-[10px]">{a.created_at?.slice(0, 10)}</span>
                          </div>
                          <p className="mt-1 text-dark-muted">{a.notes || a.summary}</p>
                        </div>
                      ))
                    ) : (
                      <div className="p-8 text-center text-xs text-dark-muted">No activities logged yet.</div>
                    )}
                  </div>
                )}

                {/* TAB: RESEARCH */}
                {activeTab === "research" && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold uppercase text-dark-muted mb-2">Public Web Research</h3>
                      <div className="space-y-2">
                        {c360?.web_research?.length > 0 ? (
                          c360.web_research.map((r) => (
                            <div key={r.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                              <a href={r.url} target="_blank" rel="noreferrer" className="font-medium text-brand-cyan hover:underline flex items-center gap-1">
                                <span>{r.title || r.url}</span>
                                <ExternalLink className="h-3 w-3" />
                              </a>
                              <p className="mt-1 text-dark-muted">{r.snippet}</p>
                            </div>
                          ))
                        ) : (
                          <div className="p-6 text-center text-xs text-dark-muted">No web research items captured.</div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 24-FIELD RESEARCH BRIEF MODAL */}
      {briefModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in">
          <div className="dark-card w-full max-w-3xl max-h-[90vh] flex flex-col border border-brand-primary/40 shadow-2xl overflow-hidden">
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

            <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
              {briefModal.loading ? (
                <div className="p-12 text-center text-dark-muted">
                  <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-brand-primary" />
                  <span>Loading 24-field research brief...</span>
                </div>
              ) : briefModal.data ? (
                <div className="space-y-4">
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
              <button onClick={() => setRejectModal({ open: false, candidateId: null, reason: "company_mismatch", notes: "" })} className="text-dark-muted hover:text-white">✕</button>
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
                onClick={() => setRejectModal({ open: false, candidateId: null, reason: "company_mismatch", notes: "" })}
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

function CandidateCard({ c, onEnrich, onVerify, onReject, enrichingId, isPrimary = false }) {
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
      className={`rounded-xl border p-4 text-xs transition ${
        isPrimary
          ? "border-brand-primary/50 bg-gradient-to-r from-brand-primary/10 via-dark-panel to-dark-panel"
          : "border-dark-border bg-dark-panel"
      }`}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-dark-border/60">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-sm text-white">{c.candidate_name || "Name Unresolved"}</span>
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

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={onEnrich}
            disabled={enrichingId === c.id || !isVerified}
            className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              isVerified
                ? "bg-cyan-600 hover:bg-cyan-500 text-white shadow"
                : "bg-dark-bg text-dark-muted border border-dark-border cursor-not-allowed opacity-60"
            }`}
            title={isVerified ? "Enrich verified contact via Apollo (Safety limit: 6 max)" : "Verification required prior to Apollo enrichment"}
          >
            <Mail className={`h-3 w-3 ${enrichingId === c.id ? "animate-spin" : ""}`} />
            <span>{enrichingId === c.id ? "Enriching..." : c.apollo_email ? "Re-enrich" : "Apollo Enrich"}</span>
          </button>

          {!isVerified && !isRejected && (
            <button
              onClick={onVerify}
              className="flex items-center gap-1 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/20 transition"
              title="Manually verify candidate"
            >
              <UserCheck className="h-3 w-3" />
              <span>Verify</span>
            </button>
          )}

          {!isRejected && (
            <button
              onClick={onReject}
              className="flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1.5 text-xs text-rose-400 hover:bg-rose-500/20 transition"
              title="Reject candidate with reason"
            >
              <UserX className="h-3 w-3" />
              <span>Reject</span>
            </button>
          )}
        </div>
      </div>

      {/* 5-Dimension Score Breakdown */}
      <div className="mt-3 space-y-1.5 bg-dark-bg/60 p-3 rounded-lg border border-dark-border/40">
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-semibold text-white">Verification Match Score:</span>
          <span className="font-mono font-bold text-brand-emerald">
            {((c.score_composite || 0) * 100).toFixed(0)}% ({(c.score_composite || 0).toFixed(2)} / 1.00)
          </span>
        </div>

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
}
