import React, { useCallback, useEffect, useState } from "react";
import { Play, Square, RefreshCw, ShieldCheck } from "lucide-react";
import { getOperatorStatus, startOperator, stopOperator } from "../api";

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

  const refresh = useCallback(async () => {
    try {
      const response = await getOperatorStatus();
      setStatus(response.data);
      setError("");
    } catch (requestError) {
      setError(requestError.response?.data?.detail?.reason || requestError.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

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
