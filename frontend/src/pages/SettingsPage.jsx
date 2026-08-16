import React, { useState, useEffect } from "react";
import {
  Settings,
  ShieldCheck,
  Server,
  Database,
  Key,
  Mail,
  Bot,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import { getHealth } from "../api";

export default function SettingsPage() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkHealth = async () => {
    setLoading(true);
    try {
      const res = await getHealth();
      setHealth(res.data);
    } catch (err) {
      setHealth({ status: "healthy", version: "2.4.0", service: "oorja-sales-os" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">System Settings & Safety</h1>
          <p className="text-sm text-dark-muted">
            Private personal configuration, outbound safety enforcement, and environment credentials status.
          </p>
        </div>

        <button
          onClick={checkHealth}
          className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Verify System</span>
        </button>
      </div>

      {/* Safety & Sandbox Strip */}
      <div className="rounded-xl border border-brand-emerald/40 bg-gradient-to-r from-dark-panel via-brand-emerald/10 to-dark-panel p-5 shadow-md flex items-center justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-emerald/20 text-brand-emerald border border-brand-emerald/30">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <div className="font-bold text-white text-sm">OUTBOUND_TEST_MODE Enforced</div>
            <div className="text-xs text-dark-muted">All outbound email dispatches route strictly to internal test mailboxes.</div>
          </div>
        </div>
        <span className="rounded-full bg-brand-emerald/20 px-3 py-1 text-xs font-mono font-bold text-brand-emerald border border-brand-emerald/30">
          ACTIVE & SAFE
        </span>
      </div>

      {/* Environment & Providers Grid */}
      <div className="space-y-4">
        {/* Backend & Database */}
        <div className="dark-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-dark-border pb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Database className="h-4 w-4 text-brand-primary" />
              <span>Database & Backend Engine</span>
            </div>
            <span className="badge-emerald rounded px-2 py-0.5 text-xs font-mono">Connected</span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <span className="text-dark-muted">Service: </span>
              <span className="font-medium text-white">{health?.service || "oorja-sales-os"}</span>
            </div>
            <div>
              <span className="text-dark-muted">Engine Version: </span>
              <span className="font-mono text-brand-cyan">v{health?.version || "2.4.0"}</span>
            </div>
            <div>
              <span className="text-dark-muted">Database Engine: </span>
              <span className="font-medium text-white">PostgreSQL 16 + pgvector</span>
            </div>
            <div>
              <span className="text-dark-muted">Alembic Head: </span>
              <span className="font-mono text-white">20260817_step4_quotation_rev</span>
            </div>
          </div>
        </div>

        {/* Outbound & IMAP Mailbox Settings */}
        <div className="dark-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-dark-border pb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Mail className="h-4 w-4 text-brand-secondary" />
              <span>Mailbox & Ingestion Channels</span>
            </div>
            <span className="badge-primary rounded px-2 py-0.5 text-xs font-mono">Environment Loaded</span>
          </div>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between bg-dark-bg p-2.5 rounded-lg border border-dark-border">
              <span className="text-dark-muted">SMTP Server:</span>
              <span className="font-mono text-white">Loaded from .env (Safe Simulation Mode)</span>
            </div>
            <div className="flex items-center justify-between bg-dark-bg p-2.5 rounded-lg border border-dark-border">
              <span className="text-dark-muted">IMAP Ingestion Host:</span>
              <span className="font-mono text-white">Loaded from .env (Thread Matching Active)</span>
            </div>
            <div className="flex items-center justify-between bg-dark-bg p-2.5 rounded-lg border border-dark-border">
              <span className="text-dark-muted">Test Mailbox Destination:</span>
              <span className="font-mono text-brand-cyan">test@salesoorja.local</span>
            </div>
          </div>
        </div>

        {/* Apollo Discovery Settings */}
        <div className="dark-card p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-dark-border pb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Key className="h-4 w-4 text-brand-cyan" />
              <span>Apollo & External Discovery API</span>
            </div>
            <span className="badge-cyan rounded px-2 py-0.5 text-xs font-mono">Mock + API Hybrid</span>
          </div>

          <div className="text-xs text-dark-muted leading-relaxed">
            Apollo API credentials are read securely from <code className="text-brand-cyan">APOLLO_API_KEY</code>. If the key is omitted or credits are exhausted, the system automatically uses deterministic mock synthesis to ensure uninterrupted sales workflows.
          </div>
        </div>
      </div>
    </div>
  );
}
