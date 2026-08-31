import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Users,
  Search,
  Filter,
  Flame,
  CheckCircle2,
  AlertTriangle,
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
} from "lucide-react";
import {
  searchApolloLeads,
  getCompanies,
  validateEmail,
  qualifyLead,
  setQualificationStatus,
  discoverAutonomousCalibrationOpportunities,
  executeApolloPilot,
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
  const [enrichingId, setEnrichingId] = useState(null);
  const [notification, setNotification] = useState("");

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

  const handleEnrichApolloContact = async (companyId, companyName) => {
    setEnrichingId(companyId);
    try {
      const res = await executeApolloPilot({
        company_id: companyId,
        company_name: companyName,
        target_role: "Quality Assurance",
        limit: 2,
      });
      setNotification(`Apollo Enrichment: ${res.data?.status} (${res.data?.contacts_extracted} contacts found within safety limit).`);
    } catch (err) {
      setNotification("Apollo enrichment failed.");
    } finally {
      setEnrichingId(null);
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
            Autonomous calibration trigger detection, second-order causal reasoning, role-specific persona identification, and Apollo enrichment.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => activeTab === "autonomous" ? handleRunAutonomousDiscovery() : loadManualLeads()}
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
            <CheckCircle2 className="h-4 w-4" />
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
            </select>
          </div>
        </div>
      </div>

      {/* TAB 1: AUTONOMOUS TRIGGER DISCOVERY */}
      {activeTab === "autonomous" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4">
            {discoveredLeads.length === 0 ? (
              <div className="dark-card p-12 text-center text-xs text-dark-muted">
                No active trigger signals found for {selectedRegion}. Click "Discover Calibration Demand" to scan configured sources.
              </div>
            ) : (
              discoveredLeads.map((cand) => (
                <div
                  key={cand.company_id}
                  className="dark-card p-5 space-y-4 hover:border-brand-primary/40 transition border border-dark-border"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-dark-border pb-3">
                    <div>
                      <div className="flex items-center gap-2.5">
                        <span className="text-base font-bold text-white hover:text-brand-cyan cursor-pointer" onClick={() => onOpenCompany(cand.company_id)}>
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
                        <Zap className="h-3.5 w-3.5" />
                        <span>{cand.event_title}</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <div className="text-right">
                        <div className="font-mono text-lg font-bold text-brand-emerald">{cand.icp_score}</div>
                        <div className="text-[10px] text-dark-muted uppercase font-mono">ICP Score</div>
                      </div>
                      <button
                        onClick={() => handleEnrichApolloContact(cand.company_id, cand.company_name)}
                        disabled={enrichingId === cand.company_id}
                        className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-2 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50"
                      >
                        <Users className="h-3.5 w-3.5" />
                        <span>{enrichingId === cand.company_id ? "Enriching..." : "Enrich Decision Maker"}</span>
                      </button>
                      <button
                        onClick={() => handleQualifyLead(cand.company_id)}
                        disabled={qualifyingId === cand.company_id}
                        className="flex items-center gap-1.5 rounded-lg border border-brand-emerald/40 bg-brand-emerald/10 px-3 py-2 text-xs font-semibold text-brand-emerald hover:bg-brand-emerald/20 transition"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        <span>Qualify</span>
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
                      <span className="text-dark-muted font-medium block mb-0.5">3. Recommended Action & Persona</span>
                      <span className="text-white/90 font-medium text-brand-amber">{cand.causality_chain?.recommended_role}</span>
                      <p className="text-[11px] text-dark-muted mt-0.5">{cand.causality_chain?.action_strategy}</p>
                    </div>
                  </div>
                </div>
              ))
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
    </div>
  );
}
