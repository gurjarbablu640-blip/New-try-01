import React, { useState } from "react";
import {
  findSimilarQuotes,
  getPriceRecommendation,
  normalizeInstrument,
  resolveInstrument,
} from "../api";

export default function QuotationIntelligence() {
  const [instrument, setInstrument] = useState("");
  const [make, setMake] = useState("");
  const [parameter, setParameter] = useState("");
  const [calibrationType, setCalibrationType] = useState("");
  const [location, setLocation] = useState("");
  const [normalized, setNormalized] = useState(null);
  const [recommendation, setRecommendation] = useState(null);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const params = () => ({
    instrument_name: instrument,
    make: make || undefined,
    parameter: parameter || undefined,
    calibration_type: calibrationType || undefined,
    location: location || undefined,
    limit: 20,
  });

  const runIntelligence = async () => {
    if (!instrument.trim()) return;
    setLoading(true);
    setError("");
    try {
      const [norm, price, similar] = await Promise.all([
        normalizeInstrument(instrument),
        getPriceRecommendation(params()),
        findSimilarQuotes(params()),
      ]);
      setNormalized(norm.data);
      setRecommendation(price.data);
      setMatches(similar.data.results || []);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Unable to load quotation intelligence");
    } finally {
      setLoading(false);
    }
  };

  const createInstrument = async () => {
    if (!instrument.trim()) return;
    setLoading(true);
    setError("");
    try {
      const response = await resolveInstrument({ instrument_name: instrument, parameter: parameter || null });
      setNormalized(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Unable to resolve instrument");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="bg-white border rounded-xl p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Quotation Intelligence</h2>
          <p className="text-sm text-gray-500">Normalize an instrument, inspect historical quotes and get an explainable price recommendation.</p>
        </div>
        {recommendation?.human_approval_required && (
          <span className="px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">Human approval required</span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        <input value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="Instrument name" className="border rounded-lg px-3 py-2 text-sm" />
        <input value={make} onChange={(e) => setMake(e.target.value)} placeholder="Make" className="border rounded-lg px-3 py-2 text-sm" />
        <input value={parameter} onChange={(e) => setParameter(e.target.value)} placeholder="Parameter" className="border rounded-lg px-3 py-2 text-sm" />
        <input value={calibrationType} onChange={(e) => setCalibrationType(e.target.value)} placeholder="Onsite / In-lab" className="border rounded-lg px-3 py-2 text-sm" />
        <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" className="border rounded-lg px-3 py-2 text-sm" />
      </div>

      <div className="flex gap-2 flex-wrap">
        <button onClick={runIntelligence} disabled={loading || !instrument.trim()} className="bg-gray-900 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-50">
          {loading ? "Analyzing..." : "Analyze quotation history"}
        </button>
        <button onClick={createInstrument} disabled={loading || !instrument.trim()} className="border px-4 py-2 rounded-lg text-sm disabled:opacity-50">
          Resolve / create instrument
        </button>
      </div>

      {error && <div className="bg-red-50 text-red-700 border border-red-200 rounded-lg p-3 text-sm">{error}</div>}

      {normalized && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Normalized instrument</div>
            <div className="font-semibold text-gray-900 mt-1">{normalized.normalized_name}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Instrument ID</div>
            <div className="font-semibold text-gray-900 mt-1">{normalized.instrument_id ?? "—"}</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-3">
            <div className="text-xs text-gray-500">Match confidence</div>
            <div className="font-semibold text-gray-900 mt-1">{Number(normalized.confidence || 0).toFixed(0)}%</div>
          </div>
        </div>
      )}

      {recommendation && (
        <div className="border rounded-lg p-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-xs text-gray-500">Recommended unit price</div>
              <div className="text-2xl font-bold text-gray-900 mt-1">
                {recommendation.recommended_unit_price == null ? "No historical price" : `₹${Number(recommendation.recommended_unit_price).toLocaleString("en-IN")}`}
              </div>
            </div>
            <div className="text-right text-xs text-gray-500">
              <div>Basis: {recommendation.basis}</div>
              <div>Samples: {recommendation.sample_size || 0}</div>
              <div>Confidence: {recommendation.confidence || 0}%</div>
            </div>
          </div>
          {recommendation.min_historical_price != null && (
            <div className="text-xs text-gray-500 mt-2">
              Historical range: ₹{Number(recommendation.min_historical_price).toLocaleString("en-IN")} – ₹{Number(recommendation.max_historical_price).toLocaleString("en-IN")}
            </div>
          )}
        </div>
      )}

      {matches.length > 0 && (
        <div>
          <h3 className="font-medium text-gray-900 mb-2">Comparable historical quote items</h3>
          <div className="overflow-x-auto border rounded-lg">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="text-left px-3 py-2">Instrument</th>
                  <th className="text-left px-3 py-2">Make / Model</th>
                  <th className="text-left px-3 py-2">Parameter</th>
                  <th className="text-right px-3 py-2">Unit Price</th>
                  <th className="text-right px-3 py-2">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {matches.map((row) => (
                  <tr key={`${row.quotation_item_id}-${row.quotation_id}`}>
                    <td className="px-3 py-2">{row.instrument_name}</td>
                    <td className="px-3 py-2">{[row.make, row.model].filter(Boolean).join(" / ") || "—"}</td>
                    <td className="px-3 py-2">{row.parameter || "—"}</td>
                    <td className="px-3 py-2 text-right">₹{Number(row.unit_price || 0).toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right">{Number(row.match_confidence || 0).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
