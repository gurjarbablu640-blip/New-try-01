import React, { useState } from "react";
import api from "../api";

export default function Company360() {
  const [companyId, setCompanyId] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const id = Number(companyId);
    if (!Number.isInteger(id) || id <= 0) {
      setError("Enter a valid company ID.");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const response = await api.get(`/company-360/${id}`);
      setData(response.data);
    } catch (err) {
      setData(null);
      setError(err?.response?.data?.detail || "Company 360 could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  const company = data?.company;
  const count = (key) => data?.[key]?.length || 0;

  return (
    <section className="rounded-2xl border bg-white p-5 shadow-sm space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Company 360</h2>
        <p className="text-sm text-gray-500">One source for CRM, buying signals, quotes, research, competitors and campaigns.</p>
      </div>

      <div className="flex gap-2">
        <input
          className="w-40 rounded-lg border px-3 py-2 text-sm"
          type="number"
          min="1"
          value={companyId}
          onChange={(e) => setCompanyId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load()}
          placeholder="Company ID"
        />
        <button onClick={load} disabled={loading} className="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white disabled:opacity-50">
          {loading ? "Loading…" : "Open Company 360"}
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {company && (
        <div className="space-y-4">
          <div className="rounded-xl bg-gray-50 p-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <div className="text-xl font-semibold text-gray-900">{company.name}</div>
                <div className="text-sm text-gray-500">{company.industry || "Industry not set"} · {company.city || ""}{company.state ? `, ${company.state}` : ""}</div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-gray-900">{Number(company.icp_score || 0).toFixed(0)}</div>
                <div className="text-xs text-gray-500">ICP score · {company.tier}</div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
              <span className="rounded-lg bg-white p-2">Intent: {Number(company.intent_velocity_score || 0).toFixed(0)}</span>
              <span className="rounded-lg bg-white p-2">Window: {company.buying_window || "unknown"}</span>
              <span className="rounded-lg bg-white p-2">NABL: {company.has_nabl ? "Yes" : "No"}</span>
              <span className="rounded-lg bg-white p-2">Order: ₹{Number(company.order_value || 0).toLocaleString("en-IN")}</span>
              <span className="rounded-lg bg-white p-2">Status: {company.lead_status}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            {["contacts", "intent_signals", "opportunities", "tasks", "quotations", "web_research"].map((key) => (
              <div key={key} className="rounded-xl border p-3">
                <div className="text-lg font-semibold">{count(key)}</div>
                <div className="text-xs text-gray-500 capitalize">{key.replaceAll("_", " ")}</div>
              </div>
            ))}
          </div>

          {company.urgency_reason && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{company.urgency_reason}</div>}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="rounded-xl border p-4"><h3 className="font-medium">Open Opportunities</h3>{data.opportunities.length ? data.opportunities.slice(0, 5).map((x) => <div key={x.id} className="mt-2 text-sm"><b>{x.name}</b> · {x.stage} · ₹{Number(x.estimated_value || 0).toLocaleString("en-IN")}</div>) : <div className="mt-2 text-sm text-gray-500">None</div>}</div>
            <div className="rounded-xl border p-4"><h3 className="font-medium">Quotation History</h3>{data.quotations.length ? data.quotations.slice(0, 5).map((x) => <div key={x.id} className="mt-2 text-sm"><b>{x.quotation_number || `#${x.id}`}</b> · ₹{Number(x.total || 0).toLocaleString("en-IN")} · {x.status}</div>) : <div className="mt-2 text-sm text-gray-500">None</div>}</div>
            <div className="rounded-xl border p-4"><h3 className="font-medium">Latest Research</h3>{data.web_research.length ? data.web_research.slice(0, 5).map((x) => <a key={x.id} href={x.url} target="_blank" rel="noreferrer" className="mt-2 block text-sm hover:underline">{x.title || x.url}</a>) : <div className="mt-2 text-sm text-gray-500">None</div>}</div>
            <div className="rounded-xl border p-4"><h3 className="font-medium">Competitor Signals</h3>{data.competitor_observations.length ? data.competitor_observations.slice(0, 5).map((x) => <div key={x.id} className="mt-2 text-sm"><b>{x.title || x.observation_type}</b><div className="text-gray-600">{x.evidence}</div></div>) : <div className="mt-2 text-sm text-gray-500">None</div>}</div>
          </div>
        </div>
      )}
    </section>
  );
}
