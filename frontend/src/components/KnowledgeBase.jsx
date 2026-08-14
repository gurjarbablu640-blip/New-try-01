import React, { useEffect, useState } from "react";
import api from "../api";

export default function KnowledgeBase() {
  const [documents, setDocuments] = useState([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");
  const load = async () => {
    try {
      const r = await api.get("/knowledge/documents");
      setDocuments(r.data.results || []);
    } catch (e) { setError(e?.response?.data?.detail || "Knowledge base unavailable."); }
  };
  useEffect(() => { load(); }, []);
  const search = async () => {
    if (!query.trim()) return;
    try {
      const r = await api.get("/knowledge/search", { params: { q: query, limit: 20 } });
      setResults(r.data.results || []); setError("");
    } catch (e) { setError(e?.response?.data?.detail || "Search failed."); }
  };
  return <section className="space-y-4 rounded-2xl border bg-white p-5 shadow-sm">
    <div><h2 className="text-lg font-semibold text-gray-900">Oorja Knowledge Base</h2><p className="text-sm text-gray-500">Source-traceable internal knowledge with fact classification.</p></div>
    <div className="flex gap-2"><input className="flex-1 rounded-lg border px-3 py-2 text-sm" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==='Enter'&&search()} placeholder="Search NABL scope, calibration capability, policy..."/><button onClick={search} className="rounded-lg bg-gray-900 px-4 py-2 text-sm text-white">Search</button></div>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
    {results.map(r=><div key={r.chunk_id} className="rounded-xl border p-3"><div className="flex gap-2 items-center"><b>{r.title}</b><span className="rounded-full bg-gray-100 px-2 py-1 text-xs">{r.classification}</span>{r.page_number&&<span className="text-xs text-gray-500">Page {r.page_number}</span>}</div><p className="mt-2 text-sm text-gray-700">{r.content}</p><div className="mt-2 text-xs text-gray-500">Source: {r.source_reference||"Internal"} · Confidence: {r.confidence}%</div></div>)}
    <div><div className="mb-2 text-sm font-medium">Indexed documents</div>{documents.length===0?<div className="text-sm text-gray-500">No documents indexed yet.</div>:documents.map(d=><div key={d.id} className="rounded-lg border bg-gray-50 p-3 mb-2"><div className="text-sm font-medium">{d.title}</div><div className="text-xs text-gray-500">{d.document_type} · {d.chunk_count} chunks{d.version?` · v${d.version}`:""}</div></div>)}</div>
  </section>;
}
