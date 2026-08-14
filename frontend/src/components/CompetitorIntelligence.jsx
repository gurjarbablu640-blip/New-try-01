import React, { useEffect, useState } from "react";
import api from "../api";

export default function CompetitorIntelligence() {
  const [competitors, setCompetitors] = useState([]);
  const [observations, setObservations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const r = await api.get("/competitors?active=true&limit=50");
      const list = r.data.results || [];
      setCompetitors(list);
      if (selected) {
        const o = await api.get(`/competitors/observations?competitor_id=${selected}&limit=20`);
        setObservations(o.data.results || []);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || "Competitor intelligence is unavailable.");
    }
  };

  useEffect(() => { load(); }, [selected]);

  return (
    <section className="space-y-4 rounded-2xl border bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Competitor Intelligence</h2>
        <p className="text-sm text-gray-500">Evidence-backed competitor profiles, strengths, weaknesses and observed market signals.</p>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {competitors.length === 0 ? (
        <div className="rounded-xl border bg-gray-50 p-4 text-sm text-gray-500">No competitor profiles have been added yet.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          {competitors.map((c) => (
            <button key={c.id} onClick={() => setSelected(c.id)} className={`rounded-xl border p-4 text-left ${selected === c.id ? "ring-2 ring-gray-900" : "hover:bg-gray-50"}`}>
              <div className="font-semibold text-gray-900">{c.name}</div>
              <div className="mt-1 text-xs text-gray-500">{c.country || "India"} · {c.observation_count || 0} observations</div>
              <div className="mt-3 text-sm text-gray-700">{c.positioning || c.service_focus || "No positioning notes yet."}</div>
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="rounded-xl border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-medium text-gray-900">Observed evidence</h3>
            <button onClick={load} className="text-xs text-gray-500 hover:text-gray-900">Refresh</button>
          </div>
          {observations.length === 0 ? (
            <div className="text-sm text-gray-500">No observations recorded for this competitor.</div>
          ) : (
            <div className="space-y-2">
              {observations.map((o) => (
                <div key={o.id} className="rounded-lg border px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">{o.title || o.observation_type}</span>
                    <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-600">{o.classification}</span>
                    <span className="text-xs text-gray-500">{o.confidence}% confidence</span>
                  </div>
                  <div className="mt-1 text-sm text-gray-700">{o.evidence}</div>
                  {o.source_url && <div className="mt-1 text-xs text-gray-500 truncate">Source: {o.source_url}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
