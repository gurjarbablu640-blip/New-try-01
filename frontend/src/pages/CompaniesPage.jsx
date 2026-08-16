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
} from "lucide-react";
import {
  getCompanies,
  getCompany360,
  getCompanyFacilities,
  getCompanyAssets,
  getNextAction,
} from "../api";

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
      } catch (err) {
        console.error("Detail load error:", err);
      } finally {
        setLoadingDetail(false);
      }
    };
    loadDetail();
  }, [selectedId]);

  const filteredCompanies = companies.filter(
    (c) =>
      c.name?.toLowerCase().includes(search.toLowerCase()) ||
      c.city?.toLowerCase().includes(search.toLowerCase()) ||
      c.industry?.toLowerCase().includes(search.toLowerCase())
  );

  const comp = c360?.company;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Companies & Account 360</h1>
          <p className="text-sm text-dark-muted">
            Unified account hub: plant facilities, customer instruments, active quotes, and CRM history.
          </p>
        </div>
      </div>

      {/* Dual Pane Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* LEFT PANE: Master Company List (4 cols) */}
        <div className="dark-card flex flex-col lg:col-span-4 h-[calc(100vh-220px)]">
          {/* Search Box */}
          <div className="p-3 border-b border-dark-border">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-dark-muted" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search account name or city..."
                className="w-full rounded-lg border border-dark-border bg-dark-bg py-1.5 pl-8 pr-3 text-xs text-white placeholder-dark-muted focus:border-brand-primary focus:outline-none"
              />
            </div>
          </div>

          {/* Company List Scroll Area */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loadingList ? (
              <div className="p-6 text-center text-xs text-dark-muted">Loading accounts...</div>
            ) : filteredCompanies.length === 0 ? (
              <div className="p-6 text-center text-xs text-dark-muted">No matching accounts found.</div>
            ) : (
              filteredCompanies.map((item) => {
                const isSelected = item.id === selectedId;
                return (
                  <div
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    className={`flex cursor-pointer items-center justify-between rounded-xl p-3 text-xs transition ${
                      isSelected
                        ? "bg-brand-primary/15 border border-brand-primary/40 shadow-sm"
                        : "border border-transparent hover:bg-dark-hover"
                    }`}
                  >
                    <div>
                      <div className={`font-semibold text-sm ${isSelected ? "text-white" : "text-white/90"}`}>
                        {item.name}
                      </div>
                      <div className="mt-0.5 text-dark-muted text-[11px] flex items-center gap-1.5">
                        <MapPin className="h-3 w-3" />
                        <span>{item.city || "Gujarat"}</span>
                        <span>•</span>
                        <span>{item.industry || "Manufacturing"}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="rounded bg-dark-bg px-2 py-0.5 font-mono text-[10px] text-brand-cyan border border-dark-border">
                        ICP {Math.round(item.icp_score || 0)}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT PANE: Company 360 Workspace (8 cols) */}
        <div className="dark-card flex flex-col lg:col-span-8 h-[calc(100vh-220px)] overflow-hidden">
          {loadingDetail ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              <div className="flex items-center gap-2">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-primary border-t-transparent"></div>
                <span>Retrieving complete Account 360 data...</span>
              </div>
            </div>
          ) : !comp ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              Select an account from the left pane to view Company 360 intelligence.
            </div>
          ) : (
            <div className="flex flex-col h-full">
              {/* Account Header Strip */}
              <div className="p-5 border-b border-dark-border bg-dark-panel">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <h2 className="text-xl font-bold text-white">{comp.name}</h2>
                      {comp.has_nabl && (
                        <span className="badge-cyan rounded px-2 py-0.5 text-[10px] font-semibold">
                          NABL ACCREDITED
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-dark-muted">
                      <span>{comp.city || "Gujarat"}{comp.state ? `, ${comp.state}` : ""}</span>
                      <span>•</span>
                      <span>{comp.industry || "Manufacturing"}</span>
                      <span>•</span>
                      <span className="font-mono text-brand-cyan">ICP Score: {Math.round(comp.icp_score || 0)}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="rounded-lg bg-dark-bg px-3 py-1.5 font-mono text-xs font-bold text-brand-emerald border border-dark-border">
                      Order: ₹{Number(comp.order_value || 0).toLocaleString("en-IN")}
                    </span>
                  </div>
                </div>

                {/* Tabs */}
                <div className="mt-4 flex border-b border-dark-border text-xs font-medium space-x-4">
                  {[
                    { id: "overview", label: "Overview & Signals" },
                    { id: "facilities", label: `Facilities (${facilities.length})` },
                    { id: "assets", label: `Customer Assets (${assets.length})` },
                    { id: "pipeline", label: `Pipeline & Quotes (${(c360?.opportunities?.length || 0) + (c360?.quotations?.length || 0)})` },
                    { id: "activities", label: `Activities (${c360?.activities?.length || 0})` },
                    { id: "research", label: "Web Research & Competitors" },
                  ].map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setActiveTab(t.id)}
                      className={`pb-2.5 transition-colors ${
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

                    {/* Contacts */}
                    <div className="dark-card p-4">
                      <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-3">
                        Plant & Quality Decision Makers ({c360?.contacts?.length || 0})
                      </div>
                      <div className="space-y-2">
                        {c360?.contacts?.map((c) => (
                          <div key={c.id} className="flex items-center justify-between rounded-lg bg-dark-bg p-2.5 text-xs">
                            <div>
                              <div className="font-semibold text-white">{c.name || c.full_name}</div>
                              <div className="text-dark-muted">{c.title || c.designation || "Quality Lead"}</div>
                            </div>
                            <div className="font-mono text-brand-cyan">{c.email}</div>
                          </div>
                        ))}
                      </div>
                    </div>
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
                            Location: {fac.industrial_estate || fac.city || "Gujarat"} • Headcount: {fac.headcount || "50-200"}
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
                    {c360?.activities?.map((act) => (
                      <div key={act.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                        <div className="flex items-center justify-between text-white font-medium">
                          <span>{act.activity_type || "Touchpoint"}</span>
                          <span className="text-dark-muted font-mono">{act.created_at?.slice(0, 10)}</span>
                        </div>
                        <div className="mt-1 text-dark-muted">{act.remarks || "Activity completed"}</div>
                      </div>
                    ))}
                  </div>
                )}

                {/* TAB: RESEARCH */}
                {activeTab === "research" && (
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xs font-semibold uppercase text-dark-muted mb-2">Competitor Intelligence</h3>
                      {c360?.competitor_observations?.map((obs) => (
                        <div key={obs.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs mb-2">
                          <div className="font-semibold text-white">{obs.title || obs.observation_type}</div>
                          <div className="mt-1 text-dark-muted">{obs.evidence}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
