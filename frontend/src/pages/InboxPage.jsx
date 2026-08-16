import React, { useState, useEffect } from "react";
import { useOutletContext, useNavigate } from "react-router-dom";
import {
  Inbox,
  Send,
  Flame,
  CheckCircle2,
  AlertCircle,
  FileText,
  Building,
  Bot,
  Plus,
  ArrowRight,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  getInboxReplies,
  createSalesOSOpportunity,
  generateQuoteFromAssets,
} from "../api";

export default function InboxPage() {
  const { onOpenCompany } = useOutletContext();
  const navigate = useNavigate();

  const [replies, setReplies] = useState([]);
  const [selectedReply, setSelectedReply] = useState(null);
  const [filterCategory, setFilterCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState("");

  const categories = [
    { id: "all", label: "All Replies" },
    { id: "INTERESTED", label: "Interested", badge: "Hot" },
    { id: "REQUESTING_QUOTE", label: "Quote Requests", badge: "Deal" },
    { id: "MEETING_REQUESTED", label: "Meeting Bookings" },
    { id: "OBJECTION", label: "Objections" },
    { id: "NOT_INTERESTED", label: "Not Interested" },
    { id: "OUT_OF_OFFICE", label: "Out of Office" },
  ];

  const loadInbox = async () => {
    setLoading(true);
    try {
      const res = await getInboxReplies({ limit: 50 });
      const list = res.data?.results || res.data || [
        {
          id: 1,
          company_id: 1,
          company_name: "Aarti Industries Ltd (Dahej Division)",
          from_email: "rajesh.patel@aarti-industries.com",
          subject: "Re: NABL Calibration Inquiry for Aarti Industries Ltd (Dahej Division)",
          body: "Hello, we received your outreach regarding NABL calibration. Yes, we would like a quotation for our pressure transmitters and thermal gauges at our Dahej plant. Please share your rate card and 48-hr turnaround details.",
          classification: {
            category: "REQUESTING_QUOTE",
            confidence: 94.0,
            summary: "Prospect requesting urgent calibration scope quotation and rate card.",
          },
          received_at: new Date().toISOString(),
          status: "Processed",
        },
      ];
      setReplies(list);
      if (list.length > 0) {
        setSelectedReply(list[0]);
      }
    } catch (err) {
      console.error("Inbox load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInbox();
  }, []);

  const filteredReplies = replies.filter((r) => {
    if (filterCategory === "all") return true;
    return r.classification?.category === filterCategory;
  });

  const handleCreateOpportunityFromReply = async () => {
    if (!selectedReply) return;
    try {
      await createSalesOSOpportunity({
        company_id: selectedReply.company_id || 1,
        name: `Inbound Calibration Deal — ${selectedReply.company_name}`,
        stage: "Proposal",
        estimated_value: 35000,
        probability: 75,
      });
      setNotification(`Opportunity created in pipeline for ${selectedReply.company_name}!`);
    } catch (err) {
      setNotification("Failed to create opportunity.");
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Sales Intelligence Inbox</h1>
          <p className="text-sm text-dark-muted">
            Inbound reply triage, deterministic intent classification, and instant CRM conversion.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadInbox}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Check Mailbox</span>
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

      {/* Three-Column Intelligence Inbox Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-220px)]">
        {/* COLUMN 1: Category Intent Filters (3 cols) */}
        <div className="dark-card p-3 lg:col-span-3 flex flex-col space-y-1 overflow-y-auto">
          <div className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wider text-dark-muted">
            Intent Categories
          </div>

          {categories.map((c) => {
            const count =
              c.id === "all"
                ? replies.length
                : replies.filter((r) => r.classification?.category === c.id).length;

            return (
              <button
                key={c.id}
                onClick={() => setFilterCategory(c.id)}
                className={`flex items-center justify-between rounded-lg px-3 py-2.5 text-xs font-medium transition ${
                  filterCategory === c.id
                    ? "bg-brand-primary text-white shadow-md"
                    : "text-dark-muted hover:bg-dark-hover hover:text-white"
                }`}
              >
                <span>{c.label}</span>
                <span className={`rounded-full px-2 py-0.2 text-[10px] font-mono ${
                  filterCategory === c.id ? "bg-white/20 text-white" : "bg-dark-bg text-dark-muted"
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* COLUMN 2: Message Threads (4 cols) */}
        <div className="dark-card p-2 lg:col-span-4 flex flex-col overflow-y-auto space-y-1.5">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-dark-muted">
            Replies ({filteredReplies.length})
          </div>

          {filteredReplies.length === 0 ? (
            <div className="p-8 text-center text-xs text-dark-muted">No messages in this folder.</div>
          ) : (
            filteredReplies.map((r, idx) => {
              const isSelected = selectedReply?.id === r.id;
              const cat = r.classification?.category || "INTERESTED";

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedReply(r)}
                  className={`cursor-pointer rounded-xl p-3 text-xs transition border ${
                    isSelected
                      ? "bg-brand-primary/15 border-brand-primary/40 shadow-sm"
                      : "border-dark-border bg-dark-card hover:bg-dark-hover"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white">{r.company_name || r.from_email}</span>
                    <span className="text-[10px] text-dark-muted font-mono">
                      {r.received_at ? r.received_at.slice(11, 16) : "Today"}
                    </span>
                  </div>

                  <div className="mt-1 font-medium text-white/90 truncate">{r.subject}</div>
                  <div className="mt-1 text-dark-muted line-clamp-2">{r.body}</div>

                  <div className="mt-2.5 flex items-center justify-between pt-2 border-t border-dark-border">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                        cat === "REQUESTING_QUOTE"
                          ? "badge-emerald"
                          : cat === "INTERESTED"
                          ? "badge-primary"
                          : "badge-amber"
                      }`}
                    >
                      {cat.replaceAll("_", " ")}
                    </span>
                    <span className="font-mono text-[10px] text-brand-cyan">
                      {Math.round(r.classification?.confidence || 90)}% conf
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* COLUMN 3: Intelligence & Triage Detail (5 cols) */}
        <div className="dark-card p-5 lg:col-span-5 flex flex-col overflow-y-auto space-y-4">
          {!selectedReply ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              Select an email thread from the inbox to inspect intent breakdown and execute next actions.
            </div>
          ) : (
            <>
              {/* Message Header */}
              <div className="pb-4 border-b border-dark-border">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-bold text-white">{selectedReply.subject}</h2>
                    <div className="mt-1 text-xs text-dark-muted">
                      From: <span className="font-mono text-brand-cyan">{selectedReply.from_email}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Intent & Triage Analysis */}
              <div className="rounded-xl border border-brand-primary/40 bg-gradient-to-br from-brand-primary/10 via-dark-panel to-dark-panel p-4 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand-cyan">
                  <Bot className="h-4 w-4" />
                  <span>AI Classification & Intent Analysis</span>
                </div>
                <div className="text-xs text-white">
                  <span className="font-semibold text-brand-emerald">{selectedReply.classification?.category}: </span>
                  {selectedReply.classification?.summary || "Prospect expressed high commercial intent for calibration services."}
                </div>
              </div>

              {/* Message Body */}
              <div className="rounded-xl border border-dark-border bg-dark-bg p-4 text-xs text-white leading-relaxed font-sans whitespace-pre-line">
                {selectedReply.body}
              </div>

              {/* Action Conversion Panel */}
              <div className="space-y-2.5 pt-3 border-t border-dark-border">
                <div className="text-xs font-semibold uppercase text-dark-muted tracking-wider">
                  Recommended Next Actions
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={handleCreateOpportunityFromReply}
                    className="flex items-center justify-center gap-1.5 rounded-lg bg-brand-primary p-2.5 text-xs font-semibold text-white shadow hover:bg-brand-primaryHover transition"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Create Opportunity</span>
                  </button>

                  <button
                    onClick={() => navigate("/quotations")}
                    className="flex items-center justify-center gap-1.5 rounded-lg bg-brand-cyan/20 border border-brand-cyan/40 p-2.5 text-xs font-semibold text-brand-cyan hover:bg-brand-cyan/30 transition"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    <span>Draft Quotation</span>
                  </button>
                </div>

                {selectedReply.company_id && (
                  <button
                    onClick={() => onOpenCompany(selectedReply.company_id)}
                    className="w-full flex items-center justify-center gap-1.5 rounded-lg border border-dark-border bg-dark-card p-2 text-xs text-white hover:bg-dark-hover transition"
                  >
                    <Building className="h-3.5 w-3.5 text-brand-primary" />
                    <span>Open Company 360 Account</span>
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
