import React, { useCallback, useEffect, useState } from "react";
import { Play, Square, RefreshCw, ShieldCheck, Send, Eye } from "lucide-react";
import {
  getOperatorStatus,
  getSingleLiveSendCandidates,
  previewSingleLiveSend,
  sendSingleLiveTest,
  startOperator,
  stopOperator,
} from "../api";

const metrics = [
  ["companies_researched", "Companies Researched"],
  ["qualified_opportunities", "Qualified Opportunities"],
  ["people_verified", "People Verified"],
  ["contacts_enriched", "Contacts Enriched"],
  ["emails_sent", "Emails Sent"],
  ["replies", "Replies"],
  ["enquiries", "Enquiries"],
];

export default function OperatorPage() {
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [liveCandidates, setLiveCandidates] = useState([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [livePreview, setLivePreview] = useState(null);
  const [liveBusy, setLiveBusy] = useState(false);
  const [liveError, setLiveError] = useState("");
  const [liveResult, setLiveResult] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const response = await getOperatorStatus();
      setStatus(response.data);
      setError("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail?.reason || requestError.message);
    }
  }, []);

  const refreshLiveCandidates = useCallback(async () => {
    try {
      const response = await getSingleLiveSendCandidates();
      const results = response.data?.results || [];
      setLiveCandidates(results);
      setSelectedCandidateId((current) => (
        results.some((item) => String(item.candidate_id) === String(current)) ? current : ""
      ));
    } catch (requestError) {
      setLiveError(requestError.response?.data?.detail || requestError.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    refreshLiveCandidates();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh, refreshLiveCandidates]);

  const runAction = async (action) => {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(detail?.errors?.join(", ") || detail?.reason || requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const running = ["RUNNING", "WAITING", "STOPPING"].includes(status?.status);
  const counters = status?.counters || {};

  const reviewSingleLiveSend = async () => {
    if (!selectedCandidateId) return;
    setLiveBusy(true);
    setLiveError("");
    setLiveResult(null);
    try {
      const response = await previewSingleLiveSend(Number(selectedCandidateId));
      setLivePreview(response.data);
    } catch (requestError) {
      setLivePreview(null);
      setLiveError(requestError.response?.data?.detail || requestError.message);
    } finally {
      setLiveBusy(false);
    }
  };

  const executeSingleLiveSend = async () => {
    if (!livePreview?.preview_token || !livePreview?.real_send_available) return;
    if (!window.confirm(livePreview.confirmation_text)) return;
    setLiveBusy(true);
    setLiveError("");
    try {
      const response = await sendSingleLiveTest(livePreview.candidate_id, livePreview.preview_token);
      setLiveResult(response.data);
      await Promise.all([refresh(), refreshLiveCandidates()]);
    } catch (requestError) {
      setLiveError(requestError.response?.data?.detail || requestError.message);
    } finally {
      setLiveBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 text-zinc-100">
      <div className="flex flex-col gap-4 border-b border-zinc-800 pb-5 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Salesoorja Operator</h1>
          <p className="mt-1 text-sm text-zinc-400">One controlled loop using the existing intelligence, qualification, and outreach chain.</p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            disabled={busy || running}
            onClick={() => runAction(startOperator)}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play className="h-4 w-4" /> START
          </button>
          <button
            type="button"
            disabled={busy || !running}
            onClick={() => runAction(stopOperator)}
            className="flex items-center gap-2 rounded-lg bg-rose-600 px-5 py-2.5 font-semibold text-white hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Square className="h-4 w-4" /> STOP
          </button>
          <button type="button" onClick={refresh} className="rounded-lg border border-zinc-700 p-2.5 text-zinc-300 hover:bg-zinc-800" title="Refresh">
            <RefreshCw className="h-5 w-5" />
          </button>
        </div>
      </div>

      {error && <div className="rounded-lg border border-rose-800 bg-rose-950/50 p-4 text-sm text-rose-200">{error}</div>}

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 md:col-span-1">
          <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Run Status</div>
          <div className={`mt-2 text-2xl font-bold ${running ? "text-emerald-400" : status?.status === "ERROR" ? "text-rose-400" : "text-zinc-200"}`}>
            {status?.status || "LOADING"}
          </div>
          <div className="mt-3 flex items-center gap-2 text-sm text-zinc-400">
            <ShieldCheck className="h-4 w-4 text-cyan-400" /> Mode: {status?.mode || "-"}
          </div>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 md:col-span-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Current</div>
          <div className="mt-2 text-lg font-semibold text-white">{status?.current_company || "No company in progress"}</div>
          <div className="mt-2 text-sm text-zinc-400">{status?.last_action || "Ready"}</div>
          {status?.last_error && <div className="mt-2 text-sm text-rose-300">{status.last_error}</div>}
        </div>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">Today</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map(([key, label]) => (
            <div key={key} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
              <div className="text-2xl font-bold text-white">{counters[key] || 0}</div>
              <div className="mt-1 text-xs text-zinc-500">{label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-amber-800/60 bg-zinc-900 p-5">
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-300">Single Live Customer Test</h2>
            <p className="mt-1 text-sm text-zinc-400">Select exactly one existing qualified contact, review the complete email, then confirm one initial send.</p>
          </div>
          <div className="rounded-full border border-zinc-700 px-3 py-1 text-xs text-zinc-300">1 prospect · CC Bablu · BCC 0</div>
        </div>

        {liveError && <div className="mt-4 rounded-lg border border-rose-800 bg-rose-950/50 p-3 text-sm text-rose-200">{liveError}</div>}
        {liveResult && <div className="mt-4 rounded-lg border border-emerald-800 bg-emerald-950/50 p-3 text-sm text-emerald-200">Sent once at {liveResult.sent_at}. Duplicate protection is now active.</div>}

        <div className="mt-5 flex flex-col gap-3 md:flex-row">
          <select
            value={selectedCandidateId}
            onChange={(event) => {
              setSelectedCandidateId(event.target.value);
              setLivePreview(null);
              setLiveResult(null);
            }}
            className="min-w-0 flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-100"
          >
            <option value="">Choose one qualified customer contact</option>
            {liveCandidates.map((candidate) => (
              <option key={candidate.candidate_id} value={candidate.candidate_id}>
                {candidate.company} — {candidate.person} ({candidate.designation})
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={liveBusy || !selectedCandidateId || running}
            onClick={reviewSingleLiveSend}
            className="flex items-center justify-center gap-2 rounded-lg border border-cyan-700 px-4 py-2.5 text-sm font-semibold text-cyan-300 hover:bg-cyan-950/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Eye className="h-4 w-4" /> Review 1 Customer
          </button>
        </div>

        {liveCandidates.length === 0 && (
          <p className="mt-3 text-sm text-zinc-500">No existing contact currently passes every employment, facility, authority, verified-contact, personalization, and suppression gate.</p>
        )}

        {livePreview && (
          <div className="mt-5 space-y-4 border-t border-zinc-800 pt-5">
            <dl className="grid gap-3 text-sm md:grid-cols-2">
              {[
                ["Company", livePreview.company], ["Facility", livePreview.facility],
                ["Person", livePreview.person], ["Designation", livePreview.designation],
                ["Email", livePreview.email], ["Trigger", livePreview.trigger],
                ["Person score", livePreview.person_score], ["Personalization score", livePreview.personalization_score],
                ["Current employment", livePreview.current_employment], ["Facility relationship", livePreview.facility_relationship],
                ["Function", livePreview.function], ["Authority", livePreview.authority],
                ["Claim validation", livePreview.claim_validation], ["Subject", livePreview.subject],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg bg-zinc-950 p-3">
                  <dt className="text-xs uppercase tracking-wide text-zinc-500">{label}</dt>
                  <dd className="mt-1 break-words text-zinc-200">{value ?? "-"}</dd>
                </div>
              ))}
            </dl>
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Full Email Body</div>
              <iframe
                title="Single live customer email preview"
                sandbox=""
                srcDoc={livePreview.body_html}
                className="h-96 w-full rounded-lg border border-zinc-700 bg-white"
              />
            </div>
            <div className="rounded-lg border border-amber-800 bg-amber-950/30 p-4 text-sm text-amber-100 whitespace-pre-line">
              {livePreview.confirmation_text}
            </div>
            {!livePreview.real_send_available && (
              <p className="text-sm text-zinc-400">Live dispatch remains locked. Enable only `SINGLE_LIVE_CUSTOMER_TEST_ENABLED=true` for the controlled send runtime.</p>
            )}
            <button
              type="button"
              disabled={liveBusy || running || !livePreview.real_send_available}
              onClick={executeSingleLiveSend}
              className="flex items-center gap-2 rounded-lg bg-rose-600 px-5 py-2.5 font-semibold text-white hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" /> SEND LIVE TEST
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Run Window</h2>
          <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <dt className="text-zinc-500">Started</dt><dd className="text-right text-zinc-200">{status?.started_at || "-"}</dd>
            <dt className="text-zinc-500">Ended</dt><dd className="text-right text-zinc-200">{status?.ended_at || "-"}</dd>
            <dt className="text-zinc-500">Working hours</dt><dd className="text-right text-zinc-200">{status?.start_time} - {status?.end_time}</dd>
            <dt className="text-zinc-500">Daily target / max</dt><dd className="text-right text-zinc-200">{status?.daily_send_target} / {status?.daily_send_max}</dd>
          </dl>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">Provider Usage</h2>
          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            {Object.entries(status?.provider_usage || {}).map(([name, count]) => (
              <React.Fragment key={name}><span className="text-zinc-500">{name}</span><span className="text-right text-zinc-200">{count}</span></React.Fragment>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
