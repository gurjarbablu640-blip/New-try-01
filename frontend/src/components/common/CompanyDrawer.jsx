import React, { useState, useEffect } from "react";
import {
  X,
  Building,
  MapPin,
  Flame,
  Gauge,
  FileText,
  Clock,
  Send,
  ShieldAlert,
  Search,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  Plus,
  ExternalLink,
  Bot,
} from "lucide-react";
import { getCompany360, getCompanyFacilities, getCompanyAssets, getNextAction } from "../../api";

export default function CompanyDrawer({ companyId, onClose }) {
  const [data, setData] = useState(null);
  const [facilities, setFacilities] = useState([]);
  const [assets, setAssets] = useState([]);
  const [nextAction, setNextAction] = useState(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!companyId) return;

    const loadData = async () => {
      setLoading(true);
      setError("");
      try {
        const [c360Res, facRes, astRes, nbaRes] = await Promise.allSettled([
          getCompany360(companyId),
          getCompanyFacilities(companyId),
          getCompanyAssets(companyId),
          getNextAction(companyId),
        ]);

        if (c360Res.status === "fulfilled") setData(c360Res.value.data);
        if (facRes.status === "fulfilled") setFacilities(facRes.value.data?.results || facRes.value.data || []);
        if (astRes.status === "fulfilled") setAssets(astRes.value.data?.results || astRes.value.data || []);
        if (nbaRes.status === "fulfilled") setNextAction(nbaRes.value.data);
      } catch (err) {
        setError("Failed to load company intelligence.");
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [companyId]);

  if (!companyId) return null;

  const comp = data?.company;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity duration-300">
      <div className="flex h-full w-full max-w-2xl flex-col border-l border-dark-border bg-dark-bg shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Drawer Header */}
        <div className="flex items-start justify-between border-b border-dark-border bg-dark-panel p-5">
          <div className="flex items-start gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-primary/15 text-brand-primary border border-brand-primary/30">
              <Building className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-white">{comp?.name || "Loading Company..."}</h2>
                {comp?.has_nabl && (
                  <span className="rounded bg-brand-cyan/20 px-2 py-0.5 text-[10px] font-semibold text-brand-cyan border border-brand-cyan/30">
                    NABL ACCREDITED
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-3 text-xs text-dark-muted">
                <span className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  {comp?.city || "Gujarat"}{comp?.state ? `, ${comp.state}` : ""}
                </span>
                <span>•</span>
                <span>{comp?.industry || "Manufacturing"}</span>
                <span>•</span>
                <span className="font-mono text-brand-cyan">ICP {Math.round(comp?.icp_score || 0)}</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-lg p-2 text-dark-muted transition hover:bg-dark-hover hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-dark-border bg-dark-panel/60 px-5 text-xs font-medium">
          {[
            { id: "overview", label: "Overview & NBA" },
            { id: "assets", label: `Facilities & Assets (${assets.length})` },
            { id: "pipeline", label: `Pipeline & Quotes (${(data?.opportunities?.length || 0) + (data?.quotations?.length || 0)})` },
            { id: "activities", label: `Outreach & Activities (${data?.contacts?.length || 0})` },
            { id: "competitors", label: "Competitors & Research" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`border-b-2 px-3 py-3 transition-colors ${
                activeTab === t.id
                  ? "border-brand-primary text-white font-semibold"
                  : "border-transparent text-dark-muted hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Drawer Body Content */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading ? (
            <div className="flex h-64 items-center justify-center text-dark-muted text-sm">
              <div className="flex items-center gap-2">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-primary border-t-transparent"></div>
                <span>Retrieving Company 360 Intelligence...</span>
              </div>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
              {error}
            </div>
          ) : (
            <>
              {/* TAB 1: OVERVIEW */}
              {activeTab === "overview" && (
                <div className="space-y-4">
                  {/* Next Best Action Card */}
                  <div className="rounded-xl border border-brand-primary/40 bg-gradient-to-br from-brand-primary/15 via-dark-panel to-dark-panel p-4 shadow-lg">
                    <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand-cyan">
                      <Bot className="h-4 w-4" />
                      <span>AI Next Best Action</span>
                    </div>
                    <div className="mt-2 text-sm font-semibold text-white">
                      {nextAction?.action || comp?.urgency_reason || "Schedule calibration audit & review master list"}
                    </div>
                    <div className="mt-1 text-xs text-dark-muted">
                      Timing: <span className="text-brand-amber font-medium">{nextAction?.timing || "Within 48 hours"}</span> • Reason: {nextAction?.reason || "Active calibration buying window"}
                    </div>
                  </div>

                  {/* Account Metrics Grid */}
                  <div className="grid grid-cols-3 gap-3">
                    <div className="rounded-xl border border-dark-border bg-dark-card p-3">
                      <div className="text-[11px] text-dark-muted uppercase font-medium">Buying Window</div>
                      <div className="mt-1 text-sm font-bold text-brand-amber capitalize">
                        {(comp?.buying_window || "next_30_days").replaceAll("_", " ")}
                      </div>
                    </div>
                    <div className="rounded-xl border border-dark-border bg-dark-card p-3">
                      <div className="text-[11px] text-dark-muted uppercase font-medium">Lead Stage</div>
                      <div className="mt-1 text-sm font-bold text-white capitalize">
                        {comp?.lead_status || "Qualified"}
                      </div>
                    </div>
                    <div className="rounded-xl border border-dark-border bg-dark-card p-3">
                      <div className="text-[11px] text-dark-muted uppercase font-medium">Order Value</div>
                      <div className="mt-1 text-sm font-mono font-bold text-brand-emerald">
                        ₹{Number(comp?.order_value || 0).toLocaleString("en-IN")}
                      </div>
                    </div>
                  </div>

                  {/* Primary Decision Maker Contact */}
                  {data?.contacts?.length > 0 && (
                    <div className="rounded-xl border border-dark-border bg-dark-card p-4">
                      <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-3">
                        Key Decision Maker
                      </div>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="font-semibold text-white">{data.contacts[0].full_name || data.contacts[0].name}</div>
                          <div className="text-xs text-dark-muted">{data.contacts[0].designation || data.contacts[0].title || "Quality Lead"}</div>
                          <div className="mt-1 text-xs font-mono text-brand-cyan">{data.contacts[0].email}</div>
                        </div>
                        {data.contacts[0].phone && (
                          <div className="text-xs font-mono text-white bg-dark-panel px-2.5 py-1 rounded border border-dark-border">
                            {data.contacts[0].phone}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: FACILITIES & ASSETS */}
              {activeTab === "assets" && (
                <div className="space-y-4">
                  {/* Facilities */}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Plant Facilities ({facilities.length})
                    </div>
                    <div className="space-y-2">
                      {facilities.length > 0 ? (
                        facilities.map((fac) => (
                          <div key={fac.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3">
                            <div>
                              <div className="text-sm font-medium text-white">{fac.name}</div>
                              <div className="text-xs text-dark-muted">
                                {fac.plant_code ? `[${fac.plant_code}] ` : ""}{fac.industrial_estate || fac.city || "Gujarat"}
                              </div>
                            </div>
                            <span className="rounded bg-brand-primary/10 px-2 py-0.5 text-xs text-brand-primary font-mono">
                              Facility #{fac.id}
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                          No distinct plant facilities registered. Defaulting to main corporate facility.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Customer Assets */}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Instruments & Customer Assets ({assets.length})
                    </div>
                    <div className="space-y-2">
                      {assets.length > 0 ? (
                        assets.map((ast) => (
                          <div key={ast.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3">
                            <div>
                              <div className="text-sm font-medium text-white">{ast.instrument_name}</div>
                              <div className="text-xs text-dark-muted">
                                {ast.parameter} • {ast.make_model || "Standard"} • Due: <span className="text-brand-amber font-mono font-medium">{ast.calibration_due_date || "Upcoming"}</span>
                              </div>
                            </div>
                            <span className="rounded bg-brand-cyan/15 px-2 py-0.5 text-xs text-brand-cyan border border-brand-cyan/30">
                              NABL In-House
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                          No instruments on record. Generate quote from template or add customer assets.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: PIPELINE & QUOTES */}
              {activeTab === "pipeline" && (
                <div className="space-y-4">
                  {/* Opportunities */}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Opportunities ({data?.opportunities?.length || 0})
                    </div>
                    <div className="space-y-2">
                      {(data?.opportunities?.length || 0) > 0 ? (
                        data.opportunities.map((opp) => (
                          <div key={opp.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3">
                            <div>
                              <div className="text-sm font-medium text-white">{opp.name}</div>
                              <div className="text-xs text-dark-muted">
                                Stage: <span className="text-brand-cyan font-medium">{opp.stage}</span> • Probability: {opp.probability}%
                              </div>
                            </div>
                            <div className="font-mono text-sm font-bold text-white">
                              ₹{Number(opp.estimated_value || 0).toLocaleString("en-IN")}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                          No open opportunities.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Quotations */}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Quotations & Revisions ({data?.quotations?.length || 0})
                    </div>
                    <div className="space-y-2">
                      {(data?.quotations?.length || 0) > 0 ? (
                        data.quotations.map((q) => (
                          <div key={q.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3">
                            <div>
                              <div className="text-sm font-medium text-white flex items-center gap-2">
                                <span>{q.quotation_number || `Quote #${q.id}`}</span>
                                <span className="rounded bg-brand-primary/20 px-1.5 py-0.2 text-[10px] font-mono text-brand-primary">
                                  v{q.version_number || 1}
                                </span>
                              </div>
                              <div className="text-xs text-dark-muted">Status: {q.status}</div>
                            </div>
                            <div className="font-mono text-sm font-bold text-brand-emerald">
                              ₹{Number(q.total || 0).toLocaleString("en-IN")}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                          No quotation history.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: ACTIVITIES */}
              {activeTab === "activities" && (
                <div className="space-y-3">
                  <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                    Recent Interactions & Outbound
                  </div>
                  {(data?.activities?.length || 0) > 0 ? (
                    data.activities.map((act) => (
                      <div key={act.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                        <div className="flex items-center justify-between text-white font-medium">
                          <span>{act.activity_type || "Note"}</span>
                          <span className="text-dark-muted font-mono">{act.created_at?.slice(0, 10)}</span>
                        </div>
                        <div className="mt-1 text-dark-muted">{act.remarks || "Completed activity"}</div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                      No outreach activity recorded yet.
                    </div>
                  )}
                </div>
              )}

              {/* TAB 5: COMPETITORS & RESEARCH */}
              {activeTab === "competitors" && (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Observed Competitors
                    </div>
                    {(data?.competitor_observations?.length || 0) > 0 ? (
                      data.competitor_observations.map((obs) => (
                        <div key={obs.id} className="rounded-xl border border-dark-border bg-dark-card p-3 text-xs mb-2">
                          <div className="font-semibold text-white">{obs.title || obs.observation_type}</div>
                          <div className="mt-1 text-dark-muted">{obs.evidence}</div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-xl border border-dark-border bg-dark-card p-4 text-center text-xs text-dark-muted">
                        No incumbent competitors observed. Standard Oorja 48-hr turnaround pitch applies.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
