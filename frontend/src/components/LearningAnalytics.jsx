import React, { useEffect, useState } from "react";
import api from "../api";

export default function LearningAnalytics() {
  const [learning, setLearning] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [leadQuality, setLeadQuality] = useState([]);
  const [patterns, setPatterns] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const [l, a, q, p] = await Promise.all([
        api.get("/learning/summary"),
        api.get("/analytics/overview?days=90"),
        api.get("/analytics/lead-quality"),
        api.get("/learning/patterns?status=Candidate&limit=8"),
      ]);
      setLearning(l.data);
      setAnalytics(a.data);
      setLeadQuality(q.data.results || []);
      setPatterns(p.data.results || []);
    } catch (e) {
      setError(e?.response?.data?.detail || "Learning analytics could not be loaded.");
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <section className="space-y-4 rounded-2xl border bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Learning & Sales Analytics</h2>
          <p className="text-sm text-gray-500">Closed-loop visibility across pipeline, quotations, campaigns and AI feedback.</p>
        </div>
        <button onClick={load} className="rounded-lg border px-3 py-2 text-sm hover:bg-gray-50">Refresh</button>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="Feedback events" value={learning?.feedback_events ?? "—"} />
        <Metric label="Candidate rules" value={learning?.candidate_rules ?? "—"} />
        <Metric label="Approved rules" value={learning?.approved_rules ?? "—"} />
        <Metric label="Open pipeline" value={analytics ? `₹${Number(analytics.pipeline?.open_value || 0).toLocaleString("en-IN")}` : "—"} />
        <Metric label="Win rate" value={analytics?.conversion?.win_rate == null ? "—" : `${analytics.conversion.win_rate}%`} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border p-4">
          <h3 className="mb-3 font-medium text-gray-900">Pipeline & quotation health</h3>
          <div className="space-y-2 text-sm text-gray-700">
            <div className="flex justify-between"><span>Open opportunities</span><b>{analytics?.pipeline?.open_opportunities ?? "—"}</b></div>
            <div className="flex justify-between"><span>Won opportunities</span><b>{analytics?.pipeline?.won_opportunities ?? "—"}</b></div>
            <div className="flex justify-between"><span>Lost opportunities</span><b>{analytics?.pipeline?.lost_opportunities ?? "—"}</b></div>
            <div className="flex justify-between"><span>Draft quotations</span><b>{analytics?.quotations?.draft ?? "—"}</b></div>
            <div className="flex justify-between"><span>Approved quotations</span><b>{analytics?.quotations?.approved_in_period ?? "—"}</b></div>
          </div>
        </div>

        <div className="rounded-xl border p-4">
          <h3 className="mb-3 font-medium text-gray-900">Lead quality by tier</h3>
          {leadQuality.length === 0 ? <p className="text-sm text-gray-500">No lead-quality data yet.</p> : (
            <div className="space-y-2">
              {leadQuality.map((row) => (
                <div key={row.tier} className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-sm">
                  <span>{row.tier}</span>
                  <span>{row.lead_count} leads · avg ICP {row.average_icp}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="rounded-xl border p-4">
        <h3 className="mb-3 font-medium text-gray-900">Candidate learning rules</h3>
        {patterns.length === 0 ? <p className="text-sm text-gray-500">No candidate patterns yet. AI feedback and outcomes will generate them.</p> : (
          <div className="space-y-2">
            {patterns.map((r) => (
              <div key={r.id} className="rounded-lg border px-3 py-2">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-gray-900">{r.rule_key}</div>
                    <div className="text-xs text-gray-500">{r.rule_type} · evidence {r.evidence_count}</div>
                  </div>
                  <span className="rounded-full bg-amber-100 px-2 py-1 text-xs text-amber-800">{Number(r.confidence || 0).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value }) {
  return <div className="rounded-xl border bg-gray-50 p-3"><div className="text-xs uppercase tracking-wide text-gray-500">{label}</div><div className="mt-1 text-xl font-bold text-gray-900">{value}</div></div>;
}
