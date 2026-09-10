import React, { useEffect, useState } from "react";
import { getCompanies, getContactResearchStatus, getContactResearchRuns, getContactResearchRun, startContactResearchRun } from "../api";

const box = "rounded-xl border border-dark-border bg-dark-panel p-4";
const button = "rounded-lg border border-dark-border px-3 py-2 text-sm text-white hover:bg-dark-hover disabled:opacity-40";
const message = (error) => typeof error?.response?.data?.detail === "string" ? error.response.data.detail : error?.message || "Request failed. Please retry.";
const words = (value) => String(value || "Unverified").replaceAll("_", " ").toLowerCase();
const link = (value) => /^https?:\/\//i.test(value || "") ? value : undefined;
const active = (run) => ["queued", "running", "pending"].includes(String(run?.status).toLowerCase());

export default function ContactResearchPanel() {
  const [providers, setProviders] = useState([]);
  const [history, setHistory] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [selected, setSelected] = useState({});
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [run, setRun] = useState(null);
  const [starting, setStarting] = useState(false);
  const [activeRun, setActiveRun] = useState(null);
  const [apollo, setApollo] = useState(false);
  const [maxQueries, setMaxQueries] = useState(3);
  const [pollError, setPollError] = useState("");
  const [offset, setOffset] = useState(0);
  const [totalCompanies, setTotalCompanies] = useState(0);
  const selectedIds = Object.keys(selected).map(Number);
  const apolloAvailable = providers.some(p => p.id === "apollo" && p.configured && p.available);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([getContactResearchStatus(), getContactResearchRuns()]).then(([status, runs]) => {
      if (!alive) return;
      if (status.status === "fulfilled") setProviders(status.value.data.providers || []);
      else setError(message(status.reason));
      if (runs.status === "fulfilled") {
        const items = runs.value.data.runs || runs.value.data.results || (Array.isArray(runs.value.data) ? runs.value.data : []);
        setHistory(items);
        const pending = items.find(active);
        if (pending) { setActiveRun(pending); setRun(pending); }
      }
      else setError(message(runs.reason));
    });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    const timer = setTimeout(() => getCompanies({ q: query, limit: 50, offset }).then(({ data }) => {
      if (!alive) return;
      setCompanies(data.results || []);
      setTotalCompanies(data.total || 0);
    }).catch(e => { if (alive) setError(message(e)); }).finally(() => { if (alive) setLoading(false); }), 250);
    return () => { alive = false; clearTimeout(timer); };
  }, [query, offset]);

  useEffect(() => {
    if (!active(activeRun)) return;
    let alive = true;
    const timer = setTimeout(async () => {
      try {
        const { data } = await getContactResearchRun(activeRun.id);
        if (!alive) return;
        setActiveRun(data);
        setRun(previous => previous?.id === data.id ? data : previous);
        setHistory(previous => previous.map(item => item.id === data.id ? data : item));
        setPollError("");
        if (!active(data)) {
          const result = await getContactResearchRuns();
          if (alive) setHistory(result.data.runs || result.data.results || (Array.isArray(result.data) ? result.data : []));
        }
      } catch (e) {
        if (alive) { setPollError(`Progress update failed: ${message(e)} Retrying automatically.`); setActiveRun(previous => ({ ...previous })); }
      }
    }, 2000);
    return () => { alive = false; clearTimeout(timer); };
  }, [activeRun]);

  const start = async () => {
    setStarting(true); setError(""); setPollError("");
    try {
      const { data } = await startContactResearchRun({ company_ids: selectedIds, max_queries: maxQueries, use_apollo: apollo });
      setRun(data);
      setActiveRun(data);
      setHistory(previous => [data, ...previous.filter(r => r.id !== data.id)]);
    } catch (e) { setError(message(e)); }
    finally { setStarting(false); }
  };
  const openRun = async (id) => {
    try { setError(""); setRun((await getContactResearchRun(id)).data); }
    catch (e) { setError(message(e)); }
  };

  return <div className="space-y-4 text-sm text-white">
    <div className={box}>
      <h2 className="text-lg font-semibold">Free-first Contact Research</h2>
      <p className="mt-1 text-dark-muted">Select up to 50 existing companies to research Quality, QA, Metrology, Maintenance and Procurement contacts. Public evidence is retained for review; listed contact details do not establish deliverability or phone ownership.</p>
      <div className="mt-3 grid gap-2 md:grid-cols-2">{providers.map(p => <div key={p.id} className="rounded-lg bg-dark-bg p-3"><strong>{p.name}</strong><span className={p.available ? "ml-2 text-emerald-400" : "ml-2 text-amber-400"}>{p.available ? "Available" : "Skipped / unavailable"}</span><p className="mt-1 text-xs text-dark-muted">{p.reason || (p.configured ? "Configured" : "Not configured")}</p></div>)}</div>
    </div>
    {error && <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3">{error}</div>}
    <div className={box}>
      <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Choose companies · {selectedIds.length}/50 selected</h3><button className={button} onClick={() => setSelected({})}>Clear selection</button></div>
      <input aria-label="Search existing companies" className="mt-3 w-full rounded-lg border border-dark-border bg-dark-bg p-3" placeholder="Search company name…" value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} />
      <div className="mt-3 max-h-64 overflow-y-auto divide-y divide-dark-border" aria-busy={loading}>
        {loading ? <p className="py-4 text-dark-muted">Loading companies…</p> : !companies.length ? <p className="py-4 text-dark-muted">No companies found. Add companies to the CRM or change your search.</p> : companies.map(c => <label key={c.id} className="flex cursor-pointer items-start gap-3 py-3"><input type="checkbox" className="mt-1" checked={!!selected[c.id]} disabled={!selected[c.id] && selectedIds.length >= 50} onChange={e => setSelected(previous => { const next = { ...previous }; if (e.target.checked) next[c.id] = c.name; else delete next[c.id]; return next; })} /><span>{c.name}<span className="block text-xs text-dark-muted">{[c.city, c.state, c.industry].filter(Boolean).join(" · ")}</span></span></label>)}
      </div>
      <div className="mt-2 flex items-center justify-between"><button className={button} disabled={offset === 0 || loading} onClick={() => setOffset(n => Math.max(0, n - 50))}>Previous</button><span className="text-xs text-dark-muted">{totalCompanies} matching companies</span><button className={button} disabled={offset + 50 >= totalCompanies || loading} onClick={() => setOffset(n => n + 50)}>Next</button></div>
      {selectedIds.length > 0 && <p className="mt-3 text-xs text-dark-muted">Selected: {Object.values(selected).join(", ")}</p>}
      <div className="mt-4 space-y-3 border-t border-dark-border pt-4">
        <label className="flex items-center gap-3">Public search queries per company<select aria-label="Search queries per company" className="rounded bg-dark-bg p-2" value={maxQueries} onChange={e => setMaxQueries(Number(e.target.value))}>{[1, 2, 3, 4, 5, 6].map(n => <option key={n}>{n}</option>)}</select></label>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={apollo} disabled={!apolloAvailable} onChange={e => setApollo(e.target.checked)} /><span>Also use Apollo for up to 6 candidate match attempts per run. This may consume credits.<span className="block text-xs text-dark-muted">{apolloAvailable ? "Optional; off by default." : "Unavailable until an Apollo key is configured."}</span></span></label>
        <button className="rounded-lg bg-brand-primary px-4 py-2 font-semibold disabled:opacity-40" disabled={!selectedIds.length || starting || active(activeRun)} onClick={start}>{starting ? "Starting…" : active(activeRun) ? "Research in progress…" : apollo ? "Start research + Apollo" : "Start public research"}</button>
      </div>
    </div>
    <div className={box}><h3 className="font-semibold">Run history</h3>{!history.length ? <p className="mt-2 text-dark-muted">No research runs yet.</p> : <div className="mt-2 flex flex-wrap gap-2">{history.map(item => <button key={item.id} className={button} onClick={() => openRun(item.id)}>{new Date(item.created_at).toLocaleString()} · {words(item.status)} · {item.completed || 0}/{item.total || 0}</button>)}</div>}</div>
    {run && <div className="space-y-3"><div className={box}><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">Research {words(run.status)} · {run.completed || 0}/{run.total || 0} companies</h3><a className={button} href={`/api/contact-research/runs/${encodeURIComponent(run.id)}/export`} download>Export CSV</a></div><progress className="mt-3 w-full" max={run.total || 1} value={run.completed || 0} /><p className="mt-2 text-xs text-dark-muted">To retry, select the companies above and start a new run after this run finishes.</p>{pollError && <p role="alert" className="mt-2 text-amber-400">{pollError}</p>}{(run.errors || []).map((e, i) => <p key={i} className="mt-2 text-amber-400">{typeof e === "string" ? e : (e.company_id ? `Company ${e.company_id}: ` : "") + (e.message || e.error || JSON.stringify(e))}</p>)}</div>
      {(run.results || []).map((result, index) => <div key={result.company_id || index} className={box}><h4 className="font-semibold">{result.company_name} <span className="font-normal text-dark-muted">· {words(result.status)}</span></h4>{result.error && <p role="alert" className="mt-2 text-amber-400">{String(result.error)}</p>}<p className="mt-1 text-dark-muted">{result.reuse_reason || (typeof result.summary === "string" ? result.summary : "")}</p>
        {(result.candidates || []).map((candidate, n) => <div key={candidate.id || n} className="mt-3 rounded-lg border border-dark-border p-3"><strong>{candidate.name || "Unnamed candidate"}</strong><span className="ml-2 text-dark-muted">{candidate.title}</span><p className="mt-1 text-xs text-amber-300">{words(candidate.verification_status)} · Email: {words(candidate.email_status)}</p><p className="mt-2">Email: {candidate.email || "Not found"} · Phone: {candidate.phone || "Not found"}</p>{candidate.phone && <p className="text-xs text-dark-muted">Phone ownership and reachability unverified.</p>}<div className="mt-2 space-y-1">{(candidate.evidence || []).map((e, j) => <p key={j} className="text-xs">{link(e.url) && <a className="break-all text-brand-cyan underline" href={link(e.url)} target="_blank" rel="noopener noreferrer">{e.url}</a>}{e.snippet && <span className="block text-dark-muted">{e.snippet}</span>}</p>)}</div></div>)}
        {!result.candidates?.length && <p className="mt-3 text-dark-muted">No named decision-maker candidates found.</p>}
        {(result.public_contacts || []).length > 0 && <div className="mt-3"><h5 className="font-medium">Public contact details · association unconfirmed</h5>{result.public_contacts.map((contact, n) => <div key={n} className="mt-2 text-xs"><span>{contact.type}: {contact.value} · {words(contact.status)}</span>{link(contact.source_url) && <a className="ml-2 text-brand-cyan underline" href={link(contact.source_url)} target="_blank" rel="noopener noreferrer">Source</a>}</div>)}</div>}
        {Object.keys(result.stages || {}).length > 0 && <details className="mt-3 text-xs text-dark-muted"><summary className="cursor-pointer">Research steps</summary>{Object.entries(result.stages || {}).map(([stageName, stage], n) => <p key={n} className="mt-1">{typeof stage === "string" ? stage : [stage.name || stage.stage || stageName, stage.status, stage.reason || stage.message || stage.error].filter(Boolean).join(" · ")}</p>)}</details>}
      </div>)}
      {!run.results?.length && <p className={box}>{active(run) ? "Waiting for the first company result…" : "This run has no results. Check the errors above and provider availability."}</p>}
    </div>}
  </div>;
}
