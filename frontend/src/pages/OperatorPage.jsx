import React, { useCallback, useEffect, useState } from "react";
import {
  Play,
  Square,
  RefreshCw,
  ShieldCheck,
  Building2,
  CheckCircle2,
  Send,
  Inbox,
  HelpCircle,
  FileText,
  AlertTriangle,
  Activity,
} from "lucide-react";
import { getOperatorStatus, startOperator, stopOperator } from "../api";

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
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const handleStart = async () => {
    setBusy(true);
    setError("");
    try {
      const response = await startOperator();
      if (response.data?.started === false && response.data?.reason === "ALREADY_RUNNING") {
        // Idempotent start - already running
      }
      await refresh();
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(detail?.errors?.join(", ") || detail?.reason || requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    setError("");
    try {
      await stopOperator();
      await refresh();
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(detail?.errors?.join(", ") || detail?.reason || requestError.message);
    } finally {
      setBusy(false);
    }
  };

  const opStatus = status?.status || "IDLE";
  const isRunning = ["QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"].includes(opStatus);
  const counters = status?.counters || {};
  const finalReport = status?.final_report_email;
  const reportPath = status?.report_path;

  const kpiCards = [
    {
      key: "companies_researched",
      label: "Companies Researched",
      value: counters.companies_researched ?? 0,
      icon: Building2,
      color: "text-blue-400",
      bg: "bg-blue-950/30 border-blue-800/40",
    },
    {
      key: "qualified_opportunities",
      label: "Qualified Opportunities",
      value: counters.qualified_opportunities ?? 0,
      icon: CheckCircle2,
      color: "text-emerald-400",
      bg: "bg-emerald-950/30 border-emerald-800/40",
    },
    {
      key: "emails_sent",
      label: "Emails Sent",
      value: counters.emails_sent ?? 0,
      icon: Send,
      color: "text-cyan-400",
      bg: "bg-cyan-950/30 border-cyan-800/40",
    },
    {
      key: "replies",
      label: "Replies",
      value: counters.replies ?? 0,
      icon: Inbox,
      color: "text-purple-400",
      bg: "bg-purple-950/30 border-purple-800/40",
    },
    {
      key: "enquiries",
      label: "Enquiries",
      value: counters.enquiries ?? 0,
      icon: HelpCircle,
      color: "text-amber-400",
      bg: "bg-amber-950/30 border-amber-800/40",
    },
  ];

  const getStatusBadge = () => {
    if (opStatus === "QUEUED") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-blue-500/40 bg-blue-950/60 px-3.5 py-1 text-xs font-semibold text-blue-300">
          <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
          QUEUED IN WORKER
        </span>
      );
    }
    if (opStatus === "STARTING") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-cyan-500/40 bg-cyan-950/60 px-3.5 py-1 text-xs font-semibold text-cyan-300">
          <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          STARTING (WORKER ACK)
        </span>
      );
    }
    if (opStatus === "RUNNING") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/40 bg-emerald-950/60 px-3.5 py-1 text-xs font-semibold text-emerald-300">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          RUNNING
        </span>
      );
    }
    if (opStatus === "WAITING") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-amber-500/40 bg-amber-950/60 px-3.5 py-1 text-xs font-semibold text-amber-300">
          <span className="h-2 w-2 rounded-full bg-amber-400" />
          WAITING (WORKING HOURS)
        </span>
      );
    }
    if (opStatus === "STOPPING") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-amber-500/40 bg-amber-950/60 px-3.5 py-1 text-xs font-semibold text-amber-300">
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
          STOPPING SAFELY...
        </span>
      );
    }
    if (opStatus === "ERROR") {
      return (
        <span className="inline-flex items-center gap-2 rounded-full border border-rose-500/40 bg-rose-950/60 px-3.5 py-1 text-xs font-semibold text-rose-300">
          <span className="h-2 w-2 rounded-full bg-rose-400" />
          ERROR
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-zinc-700 bg-zinc-800/70 px-3.5 py-1 text-xs font-semibold text-zinc-300">
        <span className="h-2 w-2 rounded-full bg-zinc-400" />
        {opStatus || "STOPPED"}
      </span>
    );
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6 text-zinc-100">
      {/* Top Header & Autonomous Controls */}
      <div className="flex flex-col gap-4 border-b border-zinc-800 pb-5 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white">Salesoorja Autonomous Operator</h1>
            {getStatusBadge()}
          </div>
          <p className="mt-1 text-sm text-zinc-400">
            One-click autonomous outreach engine: discovery, qualification, personalization, Rediff transport, and follow-ups.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            id="operator-start-btn"
            disabled={busy || isRunning}
            onClick={handleStart}
            className="flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 font-semibold text-white shadow-lg shadow-emerald-900/20 hover:bg-emerald-500 transition disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play className="h-4 w-4" /> START
          </button>
          <button
            type="button"
            id="operator-stop-btn"
            disabled={busy || !isRunning}
            onClick={handleStop}
            className="flex items-center gap-2 rounded-lg bg-rose-600 px-5 py-2.5 font-semibold text-white shadow-lg shadow-rose-900/20 hover:bg-rose-500 transition disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Square className="h-4 w-4" /> STOP
          </button>
          <button
            type="button"
            onClick={refresh}
            className="rounded-lg border border-zinc-700 bg-zinc-800/80 p-2.5 text-zinc-300 hover:bg-zinc-700 hover:text-white transition"
            title="Refresh status"
          >
            <RefreshCw className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Synchronous Action Error (if any) */}
      {error && (
        <div className="rounded-lg border border-rose-800 bg-rose-950/60 p-4 text-sm text-rose-200">
          <div className="font-semibold text-rose-300">Operator Error</div>
          <div className="mt-1">{error}</div>
        </div>
      )}

      {/* Current Activity Section */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/90 p-5 shadow-sm md:col-span-2">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-zinc-500">
            <span className="flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-emerald-400" /> Current Activity
            </span>
            <span className="text-zinc-400">Mode: {status?.mode || "TEST"}</span>
          </div>
          <div className="mt-3">
            <div className="text-xs text-zinc-500 uppercase">Target Account</div>
            <div className="text-lg font-semibold text-white">
              {status?.current_company || "Idle — awaiting cycle trigger"}
            </div>
          </div>
          <div className="mt-3">
            <div className="text-xs text-zinc-500 uppercase">Current Action</div>
            <div className="mt-0.5 text-sm text-zinc-300">
              {status?.last_action || "Ready"}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-zinc-800 bg-zinc-900/90 p-5 shadow-sm">
          <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Execution Cadence</div>
          <dl className="mt-3 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-zinc-500">Window</dt>
              <dd className="font-mono text-zinc-300">{status?.start_time || "09:00"} - {status?.end_time || "18:00"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Target / Max</dt>
              <dd className="font-mono text-zinc-300">{status?.daily_send_target || 150} / {status?.daily_send_max || 250}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Started At</dt>
              <dd className="text-zinc-300 text-xs">{status?.started_at ? new Date(status.started_at).toLocaleTimeString() : "-"}</dd>
            </div>
            {status?.task_id && (
              <div className="flex justify-between">
                <dt className="text-zinc-500">Task ID</dt>
                <dd className="font-mono text-zinc-300 text-xs truncate max-w-[130px]" title={status.task_id}>{status.task_id}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-zinc-500">Heartbeat</dt>
              <dd className="font-mono text-emerald-400 text-xs">{status?.heartbeat_at ? new Date(status.heartbeat_at).toLocaleTimeString() : "-"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-zinc-500">Checkpoint</dt>
              <dd className="text-zinc-400 text-xs">{status?.last_checkpoint ? new Date(status.last_checkpoint).toLocaleTimeString() : "-"}</dd>
            </div>
          </dl>
        </div>
      </div>

      {/* 5 KPI Metric Cards */}
      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-400">Today's Operating Metrics</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {kpiCards.map((kpi) => {
            const Icon = kpi.icon;
            return (
              <div key={kpi.key} className={`rounded-xl border p-4 shadow-sm ${kpi.bg}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-zinc-400">{kpi.label}</span>
                  <Icon className={`h-4 w-4 ${kpi.color}`} />
                </div>
                <div className="mt-2 text-3xl font-bold tracking-tight text-white">{kpi.value}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Non-blocking Error Log */}
      {status?.last_error && (
        <div className="rounded-xl border border-amber-800/60 bg-amber-950/30 p-4 text-amber-200">
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            Non-Blocking System Notice
          </div>
          <div className="mt-1 text-sm text-zinc-300 font-mono">
            {status.last_error}
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            The operator automatically holds problematic accounts and continues executing without crashing.
          </div>
        </div>
      )}

      {/* Final Report Status Card */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/90 p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-emerald-400" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-200">Daily Final Report (XLSX)</h2>
          </div>
          <span className="rounded-full border border-zinc-700 bg-zinc-800 px-3 py-0.5 text-xs text-zinc-300">
            {reportPath ? "GENERATED" : "PENDING END OF RUN"}
          </span>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg bg-zinc-950/60 p-3.5 border border-zinc-800">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Spreadsheet Artifact</div>
            <div className="mt-1 font-mono text-xs text-zinc-300 break-all">
              {reportPath || "Will generate automatically at end-time, send target, or STOP"}
            </div>
          </div>

          <div className="rounded-lg bg-zinc-950/60 p-3.5 border border-zinc-800">
            <div className="text-xs font-semibold uppercase tracking-wider text-zinc-500">Email Delivery Status</div>
            <div className="mt-1 text-sm text-zinc-300">
              Status: <span className="font-semibold text-white">{finalReport?.status || "AWAITING_COMPLETION"}</span>
            </div>
            {finalReport?.to && (
              <div className="mt-1 text-xs text-zinc-400">
                To: <span className="text-zinc-200">{finalReport.to}</span>
              </div>
            )}
            {finalReport?.subject && (
              <div className="mt-1 text-xs text-zinc-400 truncate">
                Subject: <span className="text-zinc-200">{finalReport.subject}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
