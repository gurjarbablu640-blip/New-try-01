import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  FileText,
  Plus,
  GitCompare,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  Building,
  RefreshCw,
  Eye,
  ArrowRight,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import {
  getSalesOSQuotations,
  getQuotationDetail,
  getQuotationRevisions,
  compareQuotationRevisions,
  reviseQuotation,
  generateQuoteFromAssets,
  updateQuotationStatus,
  getCompanies,
  getCompanyFacilities,
} from "../api";

export default function QuotationsPage() {
  const { onOpenCompany } = useOutletContext();

  const [quotations, setQuotations] = useState([]);
  const [selectedQuote, setSelectedQuote] = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [compareData, setCompareData] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [facilities, setFacilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showReviseModal, setShowReviseModal] = useState(false);
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [notification, setNotification] = useState("");

  const [generateForm, setGenerateForm] = useState({
    company_id: "",
    facility_id: "",
    discount_pct: 0,
    payment_terms: "100% Against Delivery",
  });

  const [reviseForm, setReviseForm] = useState({
    reason: "Client requested 10% volume discount on pressure gauges",
    discount_pct: 10,
    notes: "Approved special rate for Dahej facility annual contract",
  });

  const loadQuotations = async () => {
    setLoading(true);
    try {
      const [quotesRes, compRes] = await Promise.allSettled([
        getSalesOSQuotations({ limit: 50 }),
        getCompanies({ limit: 100 }),
      ]);

      if (quotesRes.status === "fulfilled") {
        const list = quotesRes.value.data?.results || quotesRes.value.data || [];
        setQuotations(list);
        if (list.length > 0) {
          loadQuoteDetail(list[0].id);
        }
      }
      if (compRes.status === "fulfilled") {
        setCompanies(compRes.value.data?.results || compRes.value.data || []);
      }
    } catch (err) {
      console.error("Quotes load error:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadQuoteDetail = async (quoteId) => {
    try {
      const [detailRes, revRes] = await Promise.allSettled([
        getQuotationDetail(quoteId),
        getQuotationRevisions(quoteId),
      ]);

      if (detailRes.status === "fulfilled") setSelectedQuote(detailRes.value.data);
      if (revRes.status === "fulfilled") setRevisions(revRes.value.data?.revisions || []);
    } catch (err) {
      console.error("Quote detail error:", err);
    }
  };

  useEffect(() => {
    loadQuotations();
  }, []);

  const handleCompanyChangeForGenerate = async (compId) => {
    setGenerateForm({ ...generateForm, company_id: compId, facility_id: "" });
    if (!compId) return;
    try {
      const res = await getCompanyFacilities(compId);
      setFacilities(res.data?.results || res.data || []);
    } catch (err) {
      console.error("Facilities error:", err);
    }
  };

  const handleGenerateQuote = async (e) => {
    e.preventDefault();
    if (!generateForm.company_id) return;
    try {
      const res = await generateQuoteFromAssets({
        company_id: Number(generateForm.company_id),
        facility_id: generateForm.facility_id ? Number(generateForm.facility_id) : null,
        discount_pct: Number(generateForm.discount_pct || 0),
        payment_terms: generateForm.payment_terms,
      });
      setShowGenerateModal(false);
      setNotification(`Quotation ${res.data?.quotation_number || "Generated"} created from plant assets!`);
      loadQuotations();
    } catch (err) {
      setNotification("Failed to generate quotation from assets.");
    }
  };

  const handleReviseQuote = async (e) => {
    e.preventDefault();
    if (!selectedQuote) return;
    try {
      const res = await reviseQuotation(selectedQuote.id, {
        reason: reviseForm.reason,
        discount_pct: Number(reviseForm.discount_pct),
        notes: reviseForm.notes,
      });
      setShowReviseModal(false);
      setNotification(`Created Revision: ${res.data?.quotation_number} (v${res.data?.version_number})`);
      loadQuotations();
    } catch (err) {
      setNotification("Revision failed.");
    }
  };

  const handleUpdateStatus = async (newStatus) => {
    if (!selectedQuote) return;
    try {
      await updateQuotationStatus(selectedQuote.id, {
        status: newStatus,
        reason: `Marked as ${newStatus} in workspace`,
      });
      setNotification(`Quotation status updated to ${newStatus}`);
      loadQuotations();
    } catch (err) {
      setNotification("Status update failed.");
    }
  };

  const handleCompare = async (otherId) => {
    if (!selectedQuote || !otherId) return;
    try {
      const res = await compareQuotationRevisions(selectedQuote.id, otherId);
      setCompareData(res.data);
      setShowCompareModal(true);
    } catch (err) {
      setNotification("Failed to compare revisions.");
    }
  };

  const [showImportModal, setShowImportModal] = useState(false);
  const [importText, setImportText] = useState("");
  const [importCustName, setImportCustName] = useState("");
  const [importFile, setImportFile] = useState(null);
  const [importPreview, setImportPreview] = useState(null);
  const [importLoading, setImportLoading] = useState(false);

  const handleParseImport = async (e) => {
    e.preventDefault();
    setImportLoading(true);
    try {
      if (importFile) {
        const formData = new FormData();
        formData.append("file", importFile);
        const res = await uploadHistoricalQuoteDocument(formData);
        const preview = res.data?.preview;
        if (importCustName && preview) {
          preview.customer_name = importCustName;
        }
        setImportPreview(preview);
        setNotification(`Extracted ${res.data?.total_line_items_detected || 0} line items. Review and confirm ingestion.`);
      } else if (importText.trim()) {
        // Upload pasted text as TXT blob
        const textBlob = new Blob([importText], { type: "text/plain" });
        const formData = new FormData();
        formData.append("file", textBlob, "pasted_quotation.txt");
        const res = await uploadHistoricalQuoteDocument(formData);
        const preview = res.data?.preview;
        if (importCustName && preview) {
          preview.customer_name = importCustName;
        }
        setImportPreview(preview);
        setNotification(`Extracted ${res.data?.total_line_items_detected || 0} line items. Review and confirm ingestion.`);
      }
    } catch (err) {
      console.error("Quotation parse error:", err);
      const msg = err?.response?.data?.detail || err?.message || "Failed to parse historical quotation";
      setNotification(`Parse Error: ${msg}`);
    } finally {
      setImportLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!importPreview) return;
    setImportLoading(true);
    try {
      const res = await importHistoricalQuotations({
        quotation_number: importPreview.quotation_number,
        quotation_date: importPreview.quotation_date,
        customer_name: importPreview.customer_name,
        location: importPreview.location,
        subtotal: importPreview.subtotal,
        discount: importPreview.discount,
        tax: importPreview.tax,
        total: importPreview.total,
        outcome: importPreview.outcome,
        source_file: importPreview.source_file,
        data_provenance: "USER_PROVIDED_REAL_DATA",
        items: importPreview.items,
      });
      const qNum = res.data?.quotation_number || importPreview.quotation_number;
      const count = res.data?.line_items_indexed || importPreview.items?.length || 0;
      setNotification(`INGESTED SUCCESSFULLY: Quotation ${qNum} with ${count} line items persisted to PostgreSQL with USER_PROVIDED_REAL_DATA provenance!`);
      setShowImportModal(false);
      setImportPreview(null);
      setImportFile(null);
      setImportText("");
      loadQuotations();
    } catch (err) {
      console.error("Quotation import error:", err);
      const msg = err?.response?.data?.detail || err?.message || "Failed to save historical quotation";
      setNotification(`Import Error: ${msg}`);
    } finally {
      setImportLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">Quotation Intelligence & History</h1>
            <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
              REAL DATASET
            </span>
          </div>
          <p className="text-sm text-dark-muted">
            Historical quotation dataset ingestion, statistical pricing benchmarks, revision versioning, and NABL scope tagging.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center gap-1.5 rounded-lg border border-brand-cyan/40 bg-brand-cyan/10 px-3 py-1.5 text-xs font-semibold text-brand-cyan hover:bg-brand-cyan/20 transition"
          >
            <Sparkles className="h-3.5 w-3.5" />
            <span>Import Historical Quotations</span>
          </button>
          <button
            onClick={loadQuotations}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setShowGenerateModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Generate Quote from Assets</span>
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

      {/* Dual Pane Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-220px)]">
        {/* LEFT COLUMN: Quotations Master Directory (5 cols) */}
        <div className="dark-card p-3 lg:col-span-5 flex flex-col space-y-1.5 overflow-y-auto">
          <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-dark-muted">
            Quotations ({quotations.length})
          </div>

          {quotations.length === 0 ? (
            <div className="p-8 text-center text-xs text-dark-muted">No quotations generated yet.</div>
          ) : (
            quotations.map((q) => {
              const isSelected = selectedQuote?.id === q.id;
              const val = Number(q.total || q.subtotal || 0);

              return (
                <div
                  key={q.id}
                  onClick={() => {
                    setSelectedQuote(q);
                    loadQuoteDetail(q.id);
                  }}
                  className={`cursor-pointer rounded-xl p-3.5 text-xs transition border ${
                    isSelected
                      ? "bg-brand-primary/15 border-brand-primary/40 shadow-sm"
                      : "border-dark-border bg-dark-card hover:bg-dark-hover"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white text-sm">{q.quotation_number || `Quote #${q.id}`}</span>
                      <span className="rounded bg-brand-primary/20 px-1.5 py-0.2 text-[10px] font-mono text-brand-primary">
                        v{q.version_number || 1}
                      </span>
                    </div>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${
                        q.status === "Won"
                          ? "badge-emerald"
                          : q.status === "Approved"
                          ? "badge-cyan"
                          : q.status === "Sent"
                          ? "badge-primary"
                          : "badge-amber"
                      }`}
                    >
                      {q.status}
                    </span>
                  </div>

                  <div className="mt-1 font-medium text-white/90">{q.company_name || `Account #${q.company_id}`}</div>

                  <div className="mt-2.5 flex items-center justify-between pt-2 border-t border-dark-border text-xs">
                    <span className="font-mono font-bold text-brand-emerald">
                      ₹{val.toLocaleString("en-IN")}
                    </span>
                    <span className="text-dark-muted text-[11px] font-mono">
                      {q.created_at ? q.created_at.slice(0, 10) : "2026-08-17"}
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* RIGHT COLUMN: Quotation Workspace & Item Breakdown (7 cols) */}
        <div className="dark-card p-5 lg:col-span-7 flex flex-col overflow-y-auto space-y-5">
          {!selectedQuote ? (
            <div className="flex h-full items-center justify-center text-xs text-dark-muted">
              Select a quotation to inspect line items, compare revision diffs, and advance commercial status.
            </div>
          ) : (
            <>
              {/* Header Info */}
              <div className="flex items-start justify-between pb-4 border-b border-dark-border">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-white">{selectedQuote.quotation_number || `Quote #${selectedQuote.id}`}</h2>
                    <span className="badge-primary rounded px-2 py-0.5 text-xs font-mono">
                      v{selectedQuote.version_number || 1}
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${
                        selectedQuote.status === "Won"
                          ? "badge-emerald"
                          : selectedQuote.status === "Approved"
                          ? "badge-cyan"
                          : "badge-amber"
                      }`}
                    >
                      {selectedQuote.status}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-dark-muted">
                    Account: <span className="font-semibold text-white">{selectedQuote.company_name}</span> • Terms: {selectedQuote.payment_terms || "100% Against Delivery"}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowReviseModal(true)}
                    className="flex items-center gap-1 rounded-lg border border-brand-primary/40 bg-brand-primary/10 px-3 py-1.5 text-xs font-semibold text-brand-primary hover:bg-brand-primary/20 transition"
                  >
                    <GitCompare className="h-3.5 w-3.5" />
                    <span>Create Revision</span>
                  </button>
                  {selectedQuote.status !== "Won" && (
                    <button
                      onClick={() => handleUpdateStatus("Won")}
                      className="flex items-center gap-1 rounded-lg bg-brand-emerald px-3 py-1.5 text-xs font-bold text-dark-bg hover:bg-emerald-400 transition"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Mark Won</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Quotation Financial Summary */}
              <div className="grid grid-cols-4 gap-3">
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Subtotal</div>
                  <div className="mt-1 font-mono text-base font-bold text-white">
                    ₹{Number(selectedQuote.subtotal || selectedQuote.total || 0).toLocaleString("en-IN")}
                  </div>
                </div>
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">Discount</div>
                  <div className="mt-1 font-mono text-base font-bold text-brand-amber">
                    {selectedQuote.discount_pct || 0}%
                  </div>
                </div>
                <div className="dark-card p-3">
                  <div className="text-[11px] text-dark-muted uppercase">GST (18%)</div>
                  <div className="mt-1 font-mono text-base font-bold text-dark-muted">
                    ₹{Number((selectedQuote.total || 0) * 0.18).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                  </div>
                </div>
                <div className="dark-card p-3 bg-gradient-to-br from-dark-panel to-brand-primary/10 border-brand-primary/30">
                  <div className="text-[11px] text-dark-muted uppercase">Grand Total</div>
                  <div className="mt-1 font-mono text-base font-bold text-brand-emerald">
                    ₹{Number(selectedQuote.total || 0).toLocaleString("en-IN")}
                  </div>
                </div>
              </div>

              {/* Line Items Table */}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Quotation Line Items & Calibration Parameters
                </div>
                <div className="overflow-hidden rounded-xl border border-dark-border">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr>
                        <th className="dark-table-header">Description / Instrument</th>
                        <th className="dark-table-header">Qty</th>
                        <th className="dark-table-header">Rate (₹)</th>
                        <th className="dark-table-header">NABL Scope</th>
                        <th className="dark-table-header text-right">Amount (₹)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(selectedQuote.items?.length || 0) === 0 ? (
                        <tr>
                          <td colSpan={5} className="p-4 text-center text-dark-muted">Standard NABL calibration package included.</td>
                        </tr>
                      ) : (
                        selectedQuote.items.map((it, idx) => (
                          <tr key={idx} className="dark-table-row">
                            <td className="dark-table-cell font-medium text-white">{it.description || it.instrument_name}</td>
                            <td className="dark-table-cell font-mono">{it.quantity || 1}</td>
                            <td className="dark-table-cell font-mono">₹{Number(it.unit_price || 0).toLocaleString("en-IN")}</td>
                            <td className="dark-table-cell">
                              <span className="badge-cyan rounded px-1.5 py-0.5 text-[10px]">
                                {it.nabl_accredited !== false ? "NABL In-House" : "OEM Direct"}
                              </span>
                            </td>
                            <td className="dark-table-cell font-mono text-right font-bold text-white">
                              ₹{Number(it.total || (it.quantity || 1) * (it.unit_price || 0)).toLocaleString("en-IN")}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Revision History & Comparator */}
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                  Revision Lineage ({revisions.length})
                </div>
                <div className="space-y-2">
                  {revisions.length <= 1 ? (
                    <div className="rounded-xl border border-dark-border bg-dark-panel p-3 text-xs text-dark-muted">
                      Original primary version (v1). No revised iterations yet.
                    </div>
                  ) : (
                    revisions.map((rev) => (
                      <div key={rev.id} className="flex items-center justify-between rounded-xl border border-dark-border bg-dark-card p-3 text-xs">
                        <div>
                          <span className="font-semibold text-white">{rev.quotation_number}</span>
                          <span className="ml-2 font-mono text-brand-cyan">v{rev.version_number}</span>
                          <div className="text-dark-muted mt-0.5">{rev.revision_reason || "Price negotiation revision"}</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="font-mono font-bold text-brand-emerald">
                            ₹{Number(rev.total || 0).toLocaleString("en-IN")}
                          </span>
                          {rev.id !== selectedQuote.id && (
                            <button
                              onClick={() => handleCompare(rev.id)}
                              className="rounded bg-brand-primary/20 px-2 py-1 text-[11px] font-semibold text-brand-primary border border-brand-primary/30 hover:bg-brand-primary/30"
                            >
                              Diff vs Selected
                            </button>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* GENERATE FROM ASSETS MODAL */}
      {showGenerateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95">
            <h2 className="text-lg font-bold text-white mb-4">Generate Quote from Plant Assets</h2>
            <form onSubmit={handleGenerateQuote} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Customer Account</label>
                <select
                  value={generateForm.company_id}
                  onChange={(e) => handleCompanyChangeForGenerate(e.target.value)}
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                >
                  <option value="">Select Account...</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              {facilities.length > 0 && (
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Plant Facility (Optional)</label>
                  <select
                    value={generateForm.facility_id}
                    onChange={(e) => setGenerateForm({ ...generateForm, facility_id: e.target.value })}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  >
                    <option value="">All Facilities</option>
                    {facilities.map((f) => (
                      <option key={f.id} value={f.id}>{f.name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Discount %</label>
                  <input
                    type="number"
                    value={generateForm.discount_pct}
                    onChange={(e) => setGenerateForm({ ...generateForm, discount_pct: e.target.value })}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white font-mono"
                  />
                </div>
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Payment Terms</label>
                  <input
                    type="text"
                    value={generateForm.payment_terms}
                    onChange={(e) => setGenerateForm({ ...generateForm, payment_terms: e.target.value })}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowGenerateModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Generate Quote
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* REVISE MODAL */}
      {showReviseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95">
            <h2 className="text-lg font-bold text-white mb-4">Create Quotation Revision</h2>
            <form onSubmit={handleReviseQuote} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Revision Reason</label>
                <input
                  type="text"
                  value={reviseForm.reason}
                  onChange={(e) => setReviseForm({ ...reviseForm, reason: e.target.value })}
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Revised Discount %</label>
                <input
                  type="number"
                  value={reviseForm.discount_pct}
                  onChange={(e) => setReviseForm({ ...reviseForm, discount_pct: e.target.value })}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white font-mono"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Revision Notes</label>
                <textarea
                  value={reviseForm.notes}
                  onChange={(e) => setReviseForm({ ...reviseForm, notes: e.target.value })}
                  rows={2}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowReviseModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Save Revision
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* REVISION COMPARATOR DIFF MODAL */}
      {showCompareModal && compareData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95 space-y-4">
            <div className="flex items-center justify-between border-b border-dark-border pb-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <GitCompare className="h-5 w-5 text-brand-cyan" />
                <span>Side-by-Side Revision Comparison</span>
              </h2>
              <button onClick={() => setShowCompareModal(false)} className="text-dark-muted hover:text-white">✕</button>
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs">
              <div className="rounded-xl border border-dark-border bg-dark-card p-4 space-y-2">
                <div className="font-semibold text-brand-primary">Base Version ({compareData.base_version?.quotation_number})</div>
                <div>Total: <span className="font-mono font-bold text-white">₹{Number(compareData.base_version?.total || 0).toLocaleString("en-IN")}</span></div>
                <div>Discount: <span className="font-mono text-brand-amber">{compareData.base_version?.discount_pct || 0}%</span></div>
              </div>

              <div className="rounded-xl border border-dark-border bg-dark-card p-4 space-y-2">
                <div className="font-semibold text-brand-emerald">Revised Version ({compareData.target_version?.quotation_number})</div>
                <div>Total: <span className="font-mono font-bold text-brand-emerald">₹{Number(compareData.target_version?.total || 0).toLocaleString("en-IN")}</span></div>
                <div>Discount: <span className="font-mono text-brand-amber">{compareData.target_version?.discount_pct || 0}%</span></div>
              </div>
            </div>

            <div className="rounded-xl border border-brand-cyan/30 bg-brand-cyan/10 p-3 text-xs text-brand-cyan">
              <span className="font-bold">Net Difference: </span>
              ₹{Number(compareData.price_difference || 0).toLocaleString("en-IN")} ({compareData.percent_change || 0}% change)
            </div>
          </div>
        </div>
      )}

      {/* IMPORT HISTORICAL QUOTATIONS MODAL */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-dark-border pb-3">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-brand-cyan" />
                  <span>Import Historical Quotations</span>
                </h2>
                <p className="text-xs text-dark-muted">
                  Upload existing PDF/CSV/Excel quotation or paste raw text to seed genuine pricing intelligence.
                </p>
              </div>
              <button onClick={() => { setShowImportModal(false); setImportPreview(null); }} className="text-dark-muted hover:text-white">✕</button>
            </div>

            {!importPreview ? (
              <form onSubmit={handleParseImport} className="space-y-4 text-xs">
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Customer / Plant Name</label>
                  <input
                    type="text"
                    value={importCustName}
                    onChange={(e) => setImportCustName(e.target.value)}
                    placeholder="e.g. Bharat Forge Ltd or Larsen & Toubro"
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  />
                </div>

                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Upload Quotation Document (PDF / CSV / TXT)</label>
                  <input
                    type="file"
                    onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:bg-brand-primary file:text-white hover:file:bg-brand-primaryHover"
                  />
                </div>

                <div className="relative flex py-2 items-center">
                  <div className="flex-grow border-t border-dark-border"></div>
                  <span className="flex-shrink mx-3 text-dark-muted text-[10px] uppercase">Or Paste Quotation Text</span>
                  <div className="flex-grow border-t border-dark-border"></div>
                </div>

                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Raw Quotation Text / Schedule</label>
                  <textarea
                    value={importText}
                    onChange={(e) => setImportText(e.target.value)}
                    rows={5}
                    placeholder={`Quote No: Q-2025-089\nDate: 15/04/2025\nCustomer: Mahindra Heavy Engines\n1. Vernier Caliper 0-300mm Qty: 4 Rate: ₹850\n2. Digital Micrometer 0-25mm Qty: 6 Rate: ₹650\n3. Fluke 87V Multimeter Qty: 2 Rate: ₹1800`}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white font-mono text-[11px]"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-dark-border">
                  <button
                    type="button"
                    onClick={() => setShowImportModal(false)}
                    className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={importLoading || (!importFile && !importText.trim())}
                    className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50"
                  >
                    {importLoading ? "Extracting..." : "Parse & Review"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 text-xs">
                <div className="rounded-xl border border-brand-emerald/30 bg-brand-emerald/10 p-3 text-brand-emerald">
                  <div className="font-bold text-sm">Extracted Quotation: {importPreview.quotation_number}</div>
                  <div className="text-xs text-white/90 mt-1">Customer: <span className="font-semibold">{importPreview.customer_name}</span> | Date: {importPreview.quotation_date}</div>
                </div>

                <div className="border border-dark-border rounded-xl overflow-hidden">
                  <div className="bg-dark-card px-3 py-2 font-semibold text-white border-b border-dark-border">
                    Extracted Line Items ({importPreview.items?.length || 0})
                  </div>
                  <div className="max-h-48 overflow-y-auto divide-y divide-dark-border">
                    {importPreview.items?.map((it, idx) => (
                      <div key={idx} className="p-3 flex items-center justify-between">
                        <div>
                          <div className="font-medium text-white">{it.instrument_name}</div>
                          <div className="text-[11px] text-dark-muted">{it.parameter} • Qty: {it.quantity}</div>
                        </div>
                        <div className="text-right font-mono font-bold text-brand-emerald">
                          ₹{Number(it.unit_price).toLocaleString("en-IN")} / unit
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex justify-between items-center bg-dark-card p-3 rounded-xl border border-dark-border">
                  <span className="text-dark-muted">Total Quotation Value:</span>
                  <span className="text-lg font-bold font-mono text-white">₹{Number(importPreview.total).toLocaleString("en-IN")}</span>
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-dark-border">
                  <button
                    type="button"
                    onClick={() => setImportPreview(null)}
                    className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                  >
                    Back to Edit
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmImport}
                    disabled={importLoading}
                    className="rounded-lg bg-brand-emerald px-4 py-2 font-semibold text-dark-bg hover:opacity-90 shadow"
                  >
                    {importLoading ? "Ingesting..." : "Confirm & Ingest to Price Dataset"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
