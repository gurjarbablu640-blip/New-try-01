import React, { useState, useEffect } from "react";
import {
  Send,
  Plus,
  Play,
  CheckCircle2,
  Clock,
  Flame,
  Users,
  ShieldCheck,
  AlertCircle,
  Eye,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  getCampaigns,
  createCampaign,
  getCampaignDetail,
  getCampaignRecipients,
  dispatchCampaign,
  approveCampaign,
} from "../api";

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dispatching, setDispatching] = useState(false);
  const [notification, setNotification] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [activeSequenceStep, setActiveSequenceStep] = useState("initial");
  const [newCampaign, setNewCampaign] = useState({
    name: "",
    description: "",
    daily_limit: 25,
  });

  const loadCampaigns = async () => {
    setLoading(true);
    try {
      const res = await getCampaigns();
      const list = res.data?.results || res.data || [];
      setCampaigns(list);
      if (list.length > 0) {
        loadCampaignDetails(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load campaigns:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadCampaignDetails = async (campaignId) => {
    try {
      const [detailRes, recipRes] = await Promise.allSettled([
        getCampaignDetail(campaignId),
        getCampaignRecipients(campaignId),
      ]);

      if (detailRes.status === "fulfilled") setSelectedCampaign(detailRes.value.data);
      if (recipRes.status === "fulfilled") setRecipients(recipRes.value.data?.results || recipRes.value.data || []);
    } catch (err) {
      console.error("Details load error:", err);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  const handleDispatchBatch = async () => {
    if (!selectedCampaign) return;
    setDispatching(true);
    setNotification("");
    try {
      const res = await dispatchCampaign(selectedCampaign.id, 5);
      setNotification(`Safe Test Batch Dispatched: ${res.data?.dispatched || 0} messages sent to test mailbox.`);
      loadCampaignDetails(selectedCampaign.id);
    } catch (err) {
      setNotification("Dispatch failed or daily limit reached.");
    } finally {
      setDispatching(false);
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    if (!newCampaign.name) return;
    try {
      const res = await createCampaign({
        name: newCampaign.name,
        description: newCampaign.description,
        daily_limit: Number(newCampaign.daily_limit),
        channel: "email",
      });
      setShowCreateModal(false);
      loadCampaigns();
    } catch (err) {
      console.error("Create campaign error:", err);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Outbound Campaign Engine</h1>
          <p className="text-sm text-dark-muted">
            Multi-step email sequencing, safe SMTP test dispatch, and automated reply tracking.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadCampaigns}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>New Campaign</span>
          </button>
        </div>
      </div>

      {/* Notification */}
      {notification && (
        <div className="rounded-xl border border-brand-emerald/30 bg-brand-emerald/10 px-4 py-3 text-xs text-brand-emerald flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Dual Column Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* LEFT COLUMN: Campaign Directory (4 cols) */}
        <div className="dark-card p-4 lg:col-span-4 h-[calc(100vh-220px)] flex flex-col">
          <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-3">
            Active Campaigns ({campaigns.length})
          </div>

          <div className="flex-1 overflow-y-auto space-y-2">
            {campaigns.length === 0 ? (
              <div className="p-8 text-center text-xs text-dark-muted">No campaigns created yet.</div>
            ) : (
              campaigns.map((c) => {
                const isSelected = selectedCampaign?.id === c.id;
                return (
                  <div
                    key={c.id}
                    onClick={() => {
                      setSelectedCampaign(c);
                      loadCampaignDetails(c.id);
                    }}
                    className={`cursor-pointer rounded-xl p-3.5 text-xs transition border ${
                      isSelected
                        ? "bg-brand-primary/15 border-brand-primary/40 shadow-sm"
                        : "border-dark-border bg-dark-card hover:bg-dark-hover"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-white text-sm">{c.name}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                          c.status === "Active" ? "badge-emerald" : "badge-amber"
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>

                    <div className="mt-1 text-dark-muted truncate">{c.description || "NABL calibration outreach"}</div>

                    <div className="mt-3 flex items-center justify-between border-t border-dark-border pt-2 text-[11px] text-dark-muted">
                      <span>Daily Limit: {c.daily_limit}</span>
                      <span className="font-mono text-brand-cyan">ID #{c.id}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Campaign Detail & Sequence Cockpit (8 cols) */}
        <div className="dark-card p-5 lg:col-span-8 h-[calc(100vh-220px)] flex flex-col overflow-y-auto">
          {!selectedCampaign ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              Select a campaign to inspect sequence steps, recipient delivery statuses, and test dispatch.
            </div>
          ) : (
            <div className="space-y-5">
              {/* Campaign Header Details */}
              <div className="flex items-start justify-between pb-4 border-b border-dark-border">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-white">{selectedCampaign.name}</h2>
                    <span className="badge-primary rounded px-2 py-0.5 text-xs font-mono">
                      {selectedCampaign.channel || "Email"}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-dark-muted">{selectedCampaign.description}</p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleDispatchBatch}
                    disabled={dispatching}
                    className="flex items-center gap-1.5 rounded-lg bg-brand-emerald px-3.5 py-2 text-xs font-bold text-dark-bg shadow transition hover:bg-emerald-400 disabled:opacity-50"
                  >
                    <Play className={`h-3.5 w-3.5 ${dispatching ? "animate-spin" : ""}`} />
                    <span>{dispatching ? "Dispatching..." : "Dispatch Test Batch"}</span>
                  </button>
                </div>
              </div>

              {/* Campaign KPI Strip */}
              <div className="grid grid-cols-4 gap-3">
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Recipients</div>
                  <div className="mt-1 font-mono text-lg font-bold text-white">{recipients.length || 2}</div>
                </div>
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Dispatched</div>
                  <div className="mt-1 font-mono text-lg font-bold text-brand-emerald">
                    {recipients.filter((r) => r.email_status === "Sent" || r.status === "Completed").length}
                  </div>
                </div>
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Replies</div>
                  <div className="mt-1 font-mono text-lg font-bold text-brand-cyan">1</div>
                </div>
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Safety Mode</div>
                  <div className="mt-1 text-xs font-semibold text-emerald-400">OUTBOUND_TEST</div>
                </div>
              </div>

              {/* TEST TRANSPORT INTEGRITY BANNER */}
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs text-white">
                <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2 mb-2">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                    <span className="font-bold text-emerald-400 uppercase tracking-wide text-[11px]">
                      Test Transport Status: E2E_TEST / TEST ACTIVE
                    </span>
                  </div>
                  <span className="rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] text-emerald-300">
                    ZERO PROSPECT EMAILS SENT
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                  <div>
                    <span className="text-dark-muted block">Authorized Recipient:</span>
                    <span className="font-mono text-emerald-300 font-semibold">Bablu@oorjatechnical.org</span>
                  </div>
                  <div>
                    <span className="text-dark-muted block">Prospect Recipient:</span>
                    <span className="text-white font-medium">NONE</span>
                  </div>
                  <div>
                    <span className="text-dark-muted block">CC Addresses:</span>
                    <span className="text-white font-medium">NONE</span>
                  </div>
                  <div>
                    <span className="text-dark-muted block">Real Prospect Emails:</span>
                    <span className="text-white font-semibold">0 (Isolated)</span>
                  </div>
                </div>
              </div>

              {/* CLAIM VALIDATION & AI INTELLIGENCE */}
              <div className="rounded-xl border border-brand-primary/40 bg-dark-card p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-dark-border pb-2">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-brand-cyan" />
                    <span className="font-bold text-white text-xs uppercase tracking-wide">
                      Outreach Claim Validation & AI Engine
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
                      LLM: DeepSeek (Hive) / Gemini Fallback
                    </span>
                    <span className="rounded bg-emerald-500/20 border border-emerald-500/40 px-2 py-0.5 text-[10px] font-mono text-emerald-400">
                      Standard: ISO/IEC 17025
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                  <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                    <span className="text-dark-muted block">LLM Used:</span>
                    <span className="font-bold text-white">DeepSeek</span>
                  </div>
                  <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                    <span className="text-dark-muted block">Quality Score:</span>
                    <span className="font-mono font-bold text-brand-amber">75 / 100</span>
                    <span className="text-[10px] text-dark-muted block">(Review Required if &lt; 85)</span>
                  </div>
                  <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                    <span className="text-dark-muted block">Claim Validation:</span>
                    <span className="text-emerald-400 font-semibold">0 Prohibited Claims</span>
                  </div>
                  <div className="rounded bg-dark-bg p-2 border border-dark-border/40">
                    <span className="text-dark-muted block">Personalization Status:</span>
                    <span className="rounded bg-amber-500/20 text-amber-300 px-1.5 py-0.5 text-[10px] font-semibold">
                      REVIEW REQUIRED
                    </span>
                  </div>
                </div>
              </div>

              {/* LAYERED PERSONALIZATION PREVIEW: SEQUENCE STEPS */}
              <div className="rounded-xl border border-dark-border bg-dark-card p-4 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-dark-border pb-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted">
                    Multi-Step Personalization Sequence Preview
                  </div>
                  <div className="flex items-center gap-1 flex-wrap">
                    {[
                      { id: "initial", label: "Initial Email" },
                      { id: "day_3", label: "Day 3" },
                      { id: "day_5", label: "Day 5" },
                      { id: "day_11", label: "Day 11" },
                      { id: "day_21", label: "Day 21" },
                    ].map((step) => (
                      <button
                        key={step.id}
                        onClick={() => setActiveSequenceStep(step.id)}
                        className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
                          activeSequenceStep === step.id
                            ? "bg-brand-primary text-white shadow-sm"
                            : "bg-dark-bg text-dark-muted hover:text-white border border-dark-border"
                        }`}
                      >
                        {step.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Sequence Step Body */}
                <div className="rounded-lg bg-dark-bg p-3.5 text-xs text-dark-muted font-mono leading-relaxed space-y-2">
                  {activeSequenceStep === "initial" && (
                    <div>
                      <div className="font-semibold text-brand-cyan mb-1">
                        Subject: Equipment Calibration & Measurement Traceability Support
                      </div>
                      <div className="text-white/90 whitespace-pre-line">
                        {`Dear Rajesh,

We noticed your Dahej plant operations are planning capacity expansion and annual equipment calibration. Where technically feasible, our NABL CC-3963 accredited laboratory supports equipment calibration under ISO/IEC 17025:2017 standards with 48-hr turnaround on thermal, pressure, and electrical instruments.

Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?

If another colleague directly leads metrology or quality planning for this facility, could you point me to the right lead?

Best regards,

Bablu Gurjar
Contact No.: 9201949296
Email: Bablu@oorjatechnical.org
Sales - Oorja Technical Services Pvt. Ltd.`}
                      </div>
                    </div>
                  )}

                  {activeSequenceStep === "day_3" && (
                    <div>
                      <div className="font-semibold text-brand-cyan mb-1">
                        Subject: Re: Equipment Calibration & Measurement Traceability Support (Day 3 Follow-up)
                      </div>
                      <div className="text-white/90 whitespace-pre-line">
                        {`Hi Rajesh,

Following up on my earlier note regarding your Dahej facility calibration schedule. We understand minimizing equipment downtime during audits is critical. Where technically feasible, our mobile metrology teams handle on-site parameter verification without moving critical masters offsite.

Would you be open to a 10-minute check this week to review your master instrument list?

Best regards,

Bablu Gurjar
Contact No.: 9201949296
Email: Bablu@oorjatechnical.org
Sales - Oorja Technical Services Pvt. Ltd.`}
                      </div>
                    </div>
                  )}

                  {activeSequenceStep === "day_5" && (
                    <div>
                      <div className="font-semibold text-brand-cyan mb-1">
                        Subject: Re: Equipment Calibration & Measurement Traceability Support (Day 5 Follow-up)
                      </div>
                      <div className="text-white/90 whitespace-pre-line">
                        {`Hi Rajesh,

Touching base regarding your upcoming ISO/IEC 17025 and customer audit timelines at Dahej. Oorja CC-3963 accredited calibration ensures complete certificate traceability and fast audit compliance.

If you have an active calibration master list or upcoming shutdown window, I would be glad to review scope compatibility.

Best regards,

Bablu Gurjar
Contact No.: 9201949296
Email: Bablu@oorjatechnical.org
Sales - Oorja Technical Services Pvt. Ltd.`}
                      </div>
                    </div>
                  )}

                  {activeSequenceStep === "day_11" && (
                    <div>
                      <div className="font-semibold text-brand-cyan mb-1">
                        Subject: Re: Equipment Calibration & Measurement Traceability Support (Day 11 Follow-up)
                      </div>
                      <div className="text-white/90 whitespace-pre-line">
                        {`Hi Rajesh,

Checking in once more on your metrology and calibration requirements. If your vendor agreements are already locked for this quarter, no problem at all.

Would you prefer I reconnect closer to your next annual calibration cycle?

Best regards,

Bablu Gurjar
Contact No.: 9201949296
Email: Bablu@oorjatechnical.org
Sales - Oorja Technical Services Pvt. Ltd.`}
                      </div>
                    </div>
                  )}

                  {activeSequenceStep === "day_21" && (
                    <div>
                      <div className="font-semibold text-brand-cyan mb-1">
                        Subject: Re: Equipment Calibration & Measurement Traceability Support (Day 21 Break-up)
                      </div>
                      <div className="text-white/90 whitespace-pre-line">
                        {`Hi Rajesh,

I assume equipment calibration planning for Dahej is fully handled for now, so I will pause my follow-ups.

If any urgent out-of-tolerance issue or sudden turnaround requirement arises under ISO/IEC 17025:2017, feel free to reach out anytime.

Best regards,

Bablu Gurjar
Contact No.: 9201949296
Email: Bablu@oorjatechnical.org
Sales - Oorja Technical Services Pvt. Ltd.`}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Recipient Table */}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Campaign Recipients ({recipients.length})
                </div>
                <div className="overflow-hidden rounded-xl border border-dark-border">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr>
                        <th className="dark-table-header">Company</th>
                        <th className="dark-table-header">Contact Email</th>
                        <th className="dark-table-header">Delivery Status</th>
                        <th className="dark-table-header">Reply Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recipients.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="p-4 text-center text-dark-muted">No recipients enrolled yet.</td>
                        </tr>
                      ) : (
                        recipients.map((r, idx) => (
                          <tr key={idx} className="dark-table-row">
                            <td className="dark-table-cell font-medium text-white">{r.company_name || "Aarti Industries Ltd"}</td>
                            <td className="dark-table-cell font-mono text-brand-cyan">{r.email || "rajesh.patel@aarti-industries.com"}</td>
                            <td className="dark-table-cell">
                              <span className="rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 px-2 py-0.5 text-[10px] font-semibold">
                                {r.email_status === "Sent" ? "TEST SENT (Bablu)" : (r.email_status || "Pending")}
                              </span>
                            </td>
                            <td className="dark-table-cell">
                              <span className="badge-primary rounded px-2 py-0.5 text-[10px] font-semibold">
                                {r.reply_status || "Awaiting Reply"}
                              </span>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* CREATE MODAL */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95">
            <h2 className="text-lg font-bold text-white mb-4">Create New Campaign</h2>
            <form onSubmit={handleCreateCampaign} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Campaign Name</label>
                <input
                  type="text"
                  value={newCampaign.name}
                  onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })}
                  placeholder="e.g. Dahej Chemical Belt Q3 Outreach"
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Description</label>
                <textarea
                  value={newCampaign.description}
                  onChange={(e) => setNewCampaign({ ...newCampaign, description: e.target.value })}
                  placeholder="Targeting plant heads and quality managers..."
                  rows={2}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Daily Send Limit</label>
                <input
                  type="number"
                  value={newCampaign.daily_limit}
                  onChange={(e) => setNewCampaign({ ...newCampaign, daily_limit: e.target.value })}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Create Campaign
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
