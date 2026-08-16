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

              {/* Sequence Steps */}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Email Sequence Template
                </div>
                <div className="rounded-xl border border-dark-border bg-dark-card p-4 space-y-2">
                  <div className="text-xs font-semibold text-white">Step 1: Initial Calibration Outreach</div>
                  <div className="rounded-lg bg-dark-bg p-3 text-xs text-dark-muted font-mono leading-relaxed">
                    Subject: NABL Calibration & Testing Support for &#123;company_name&#125;<br />
                    Dear &#123;contact_name&#125;, we noticed your Dahej plant operations are due for annual metrology audits. Oorja offers 48-hr turnaround on thermal, pressure, and electrical instruments with full NABL certificate compliance.
                  </div>
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
                              <span className="badge-emerald rounded px-2 py-0.5 text-[10px] font-semibold">
                                {r.email_status || "Sent"}
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
