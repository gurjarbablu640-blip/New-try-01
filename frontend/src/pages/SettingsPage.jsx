import React, { useState, useEffect } from "react";
import {
  getSettingsStatus,
  updateSettings,
  testAIProvider,
  testApolloConnection,
  testSMTPConnection,
  testIMAPConnection,
} from "../api";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("ai_providers");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);

  // Form State
  const [form, setForm] = useState({
    // AI Providers
    OPENAI_API_KEY: "",
    OPENAI_MODEL: "gpt-4o",
    GOOGLE_API_KEY: "",
    ORCHESTRATOR_GEMINI_MODEL: "gemini-2.0-flash",
    ORCHESTRATOR_PRIMARY_PROVIDER: "gemini",
    ORCHESTRATOR_FALLBACK_PROVIDER: "openai",

    // Apollo
    APOLLO_API_KEY: "",

    // SMTP
    SMTP_HOST: "",
    SMTP_PORT: 587,
    SMTP_USER: "",
    SMTP_PASSWORD: "",
    SMTP_FROM_EMAIL: "sales@oorja.local",
    SMTP_FROM_NAME: "Oorja Technical Services",
    SMTP_USE_TLS: true,
    OUTBOUND_TEST_MODE: true,

    // IMAP
    IMAP_HOST: "",
    IMAP_PORT: 993,
    IMAP_USER: "",
    IMAP_PASSWORD: "",
    IMAP_USE_SSL: true,

    // Research & Calling
    SERPER_API_KEY: "",
    APIFY_API_TOKEN: "",
    PILOT_PHONE_NUMBER: "+91-9876543210",
  });

  // Diagnostic Test Results State
  const [testResults, setTestResults] = useState({});
  const [testingKey, setTestingKey] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const res = await getSettingsStatus();
      setSettings(res.data);

      // Populate form defaults from masked status
      const data = res.data;
      setForm((prev) => ({
        ...prev,
        OPENAI_API_KEY: data.ai_providers?.openai?.masked_key || "",
        OPENAI_MODEL: data.ai_providers?.openai?.model || "gpt-4o",
        GOOGLE_API_KEY: data.ai_providers?.gemini?.masked_key || "",
        ORCHESTRATOR_GEMINI_MODEL: data.ai_providers?.gemini?.model || "gemini-2.0-flash",
        ORCHESTRATOR_PRIMARY_PROVIDER: data.ai_providers?.primary_provider || "gemini",
        ORCHESTRATOR_FALLBACK_PROVIDER: data.ai_providers?.fallback_provider || "openai",

        APOLLO_API_KEY: data.apollo?.masked_key || "",

        SMTP_HOST: data.smtp?.host || "",
        SMTP_PORT: data.smtp?.port || 587,
        SMTP_USER: data.smtp?.user || "",
        SMTP_PASSWORD: data.smtp?.masked_password || "",
        SMTP_FROM_EMAIL: data.smtp?.from_email || "sales@oorja.local",
        SMTP_FROM_NAME: data.smtp?.from_name || "Oorja Technical Services",
        SMTP_USE_TLS: data.smtp?.use_tls !== undefined ? data.smtp.use_tls : true,
        OUTBOUND_TEST_MODE: data.smtp?.outbound_test_mode !== undefined ? data.smtp.outbound_test_mode : true,

        IMAP_HOST: data.imap?.host || "",
        IMAP_PORT: data.imap?.port || 993,
        IMAP_USER: data.imap?.user || "",
        IMAP_PASSWORD: data.imap?.masked_password || "",
        IMAP_USE_SSL: data.imap?.use_ssl !== undefined ? data.imap.use_ssl : true,
      }));
    } catch (err) {
      setStatusMsg({ type: "error", text: `Failed to load settings: ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e) => {
    if (e) e.preventDefault();
    try {
      setSaving(true);
      setStatusMsg(null);
      const res = await updateSettings(form);
      setSettings(res.data);
      setStatusMsg({ type: "success", text: "Settings and credentials saved securely. Runtime overrides updated." });
    } catch (err) {
      setStatusMsg({ type: "error", text: `Save failed: ${err.message}` });
    } finally {
      setSaving(false);
    }
  };

  const copySMTPToIMAP = () => {
    setForm((prev) => ({
      ...prev,
      IMAP_USER: prev.SMTP_USER,
      IMAP_PASSWORD: prev.SMTP_PASSWORD,
    }));
    setStatusMsg({ type: "info", text: "Copied SMTP username and password to IMAP mailbox." });
  };

  const runTest = async (testType, payload = null) => {
    setTestingKey(testType);
    try {
      let res;
      if (testType === "openai" || testType === "gemini") {
        res = await testAIProvider(testType);
      } else if (testType === "apollo") {
        res = await testApolloConnection();
      } else if (testType === "smtp") {
        res = await testSMTPConnection();
      } else if (testType === "imap") {
        res = await testIMAPConnection();
      }
      setTestResults((prev) => ({ ...prev, [testType]: res.data }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [testType]: { status: "SERVER_ERROR", message: err.message },
      }));
    } finally {
      setTestingKey(null);
    }
  };

  const renderStatusBadge = (configured, connectedStatus = null) => {
    if (connectedStatus === "CONNECTED") {
      return <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-900/60 text-emerald-300 border border-emerald-700">● Connected</span>;
    }
    if (connectedStatus === "AUTHENTICATION_FAILED" || connectedStatus === "CONNECTION_FAILED") {
      return <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-rose-900/60 text-rose-300 border border-rose-700">● Auth Failed</span>;
    }
    if (configured) {
      return <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-900/60 text-blue-300 border border-blue-700">● Configured</span>;
    }
    return <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700">● Not Configured</span>;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6 text-zinc-100">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between pb-4 border-b border-zinc-800 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
            <span>⚙️</span> System Settings & Integrations
          </h1>
          <p className="text-sm text-zinc-400 mt-1">
            Configure secure API credentials, AI providers, Apollo pilot limits, and email channels without editing raw .env files.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={fetchSettings}
            className="px-3 py-1.5 text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded border border-zinc-700 transition"
          >
            🔄 Reload
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-1.5 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded transition flex items-center gap-2 shadow"
          >
            {saving ? "Saving..." : "💾 Save Changes"}
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {statusMsg && (
        <div
          className={`p-4 rounded-lg text-sm border flex items-center justify-between ${
            statusMsg.type === "error"
              ? "bg-rose-950/60 border-rose-800 text-rose-200"
              : statusMsg.type === "info"
              ? "bg-blue-950/60 border-blue-800 text-blue-200"
              : "bg-emerald-950/60 border-emerald-800 text-emerald-200"
          }`}
        >
          <span>{statusMsg.text}</span>
          <button onClick={() => setStatusMsg(null)} className="text-xs opacity-70 hover:opacity-100">✕</button>
        </div>
      )}

      {/* Main Settings Tabs Layout */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Navigation Sidebar */}
        <div className="space-y-1">
          {[
            { id: "ai_providers", label: "AI Providers", icon: "🤖", badge: renderStatusBadge(settings?.ai_providers?.openai?.configured || settings?.ai_providers?.gemini?.configured) },
            { id: "apollo", label: "Apollo Data Engine", icon: "🎯", badge: renderStatusBadge(settings?.apollo?.configured) },
            { id: "smtp", label: "Outbound SMTP", icon: "📤", badge: renderStatusBadge(settings?.smtp?.configured) },
            { id: "imap", label: "Inbound IMAP", icon: "📥", badge: renderStatusBadge(settings?.imap?.configured) },
            { id: "research", label: "Web & Scrapers", icon: "🌐", badge: renderStatusBadge(settings?.research_sources?.serper_configured) },
            { id: "calling", label: "Calling & Voice", icon: "📞", badge: <span className="px-2 py-0.5 text-xs bg-amber-950 text-amber-300 rounded border border-amber-800">Pilot</span> },
            { id: "security", label: "Security & Vault", icon: "🔒", badge: <span className="px-2 py-0.5 text-xs bg-zinc-800 text-zinc-400 rounded">Masked</span> },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full text-left px-3.5 py-2.5 rounded-lg text-sm font-medium transition flex items-center justify-between ${
                activeTab === tab.id
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/40"
                  : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </div>
              <div>{tab.badge}</div>
            </button>
          ))}
        </div>

        {/* Tab Content Panes */}
        <div className="md:col-span-3 bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 shadow-xl space-y-6">
          {/* TAB 1: AI PROVIDERS */}
          {activeTab === "ai_providers" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span>🤖</span> AI Models & Providers
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Configure OpenAI and Google Gemini credentials. Fallback to deterministic internal metrology reasoning is always enabled.
                </p>
              </div>

              {/* Provider Preference Selector */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/80">
                <div>
                  <label className="block text-xs font-semibold text-zinc-300 mb-1">Primary Orchestrator Provider</label>
                  <select
                    value={form.ORCHESTRATOR_PRIMARY_PROVIDER}
                    onChange={(e) => setForm({ ...form, ORCHESTRATOR_PRIMARY_PROVIDER: e.target.value })}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                  >
                    <option value="gemini">Google Gemini (Default / Recommended)</option>
                    <option value="openai">OpenAI ChatGPT</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-300 mb-1">Fallback Provider</label>
                  <select
                    value={form.ORCHESTRATOR_FALLBACK_PROVIDER}
                    onChange={(e) => setForm({ ...form, ORCHESTRATOR_FALLBACK_PROVIDER: e.target.value })}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                  >
                    <option value="openai">OpenAI ChatGPT</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="deterministic">Internal Deterministic Logic (Zero LLM)</option>
                  </select>
                </div>
              </div>

              {/* Google Gemini Configuration */}
              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-zinc-200">Google Gemini</span>
                    {renderStatusBadge(settings?.ai_providers?.gemini?.configured, testResults.gemini?.status)}
                  </div>
                  <button
                    type="button"
                    disabled={testingKey === "gemini"}
                    onClick={() => runTest("gemini")}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-indigo-300 border border-zinc-700 rounded transition"
                  >
                    {testingKey === "gemini" ? "Testing..." : "Test Connection"}
                  </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">GOOGLE_API_KEY</label>
                    <input
                      type="password"
                      value={form.GOOGLE_API_KEY}
                      onChange={(e) => setForm({ ...form, GOOGLE_API_KEY: e.target.value })}
                      placeholder="AIzaSy••••••••"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Model Name</label>
                    <input
                      type="text"
                      value={form.ORCHESTRATOR_GEMINI_MODEL}
                      onChange={(e) => setForm({ ...form, ORCHESTRATOR_GEMINI_MODEL: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>
                {testResults.gemini && (
                  <div className={`text-xs p-2 rounded ${testResults.gemini.status === "CONNECTED" ? "bg-emerald-950/60 text-emerald-300" : "bg-rose-950/60 text-rose-300"}`}>
                    {testResults.gemini.message}
                  </div>
                )}
              </div>

              {/* OpenAI Configuration */}
              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-zinc-200">OpenAI</span>
                    {renderStatusBadge(settings?.ai_providers?.openai?.configured, testResults.openai?.status)}
                  </div>
                  <button
                    type="button"
                    disabled={testingKey === "openai"}
                    onClick={() => runTest("openai")}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-indigo-300 border border-zinc-700 rounded transition"
                  >
                    {testingKey === "openai" ? "Testing..." : "Test Connection"}
                  </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">OPENAI_API_KEY</label>
                    <input
                      type="password"
                      value={form.OPENAI_API_KEY}
                      onChange={(e) => setForm({ ...form, OPENAI_API_KEY: e.target.value })}
                      placeholder="sk-proj-••••••••"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Model Name</label>
                    <input
                      type="text"
                      value={form.OPENAI_MODEL}
                      onChange={(e) => setForm({ ...form, OPENAI_MODEL: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>
                {testResults.openai && (
                  <div className={`text-xs p-2 rounded ${testResults.openai.status === "CONNECTED" ? "bg-emerald-950/60 text-emerald-300" : "bg-rose-950/60 text-rose-300"}`}>
                    {testResults.openai.message}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 2: APOLLO */}
          {activeTab === "apollo" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span>🎯</span> Apollo Lead Discovery & Enrichment
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Industrial B2B data provider for manufacturing plant decision-makers.
                </p>
              </div>

              {/* Pilot Safety Guard Banner */}
              <div className="p-4 rounded-lg bg-amber-950/40 border border-amber-800/80 flex items-start gap-3">
                <span className="text-xl">🛡️</span>
                <div>
                  <h4 className="text-sm font-semibold text-amber-200">Live Pilot Hard Cap: Maximum 5–6 Contacts</h4>
                  <p className="text-xs text-amber-300/80 mt-1">
                    To prevent accidental credit exhaustion during pilot onboarding, the backend strictly enforces a hard limit of 6 contacts per search batch.
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm text-zinc-200">Apollo API Key</span>
                    {renderStatusBadge(settings?.apollo?.configured, testResults.apollo?.status)}
                  </div>
                  <button
                    type="button"
                    disabled={testingKey === "apollo"}
                    onClick={() => runTest("apollo")}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-indigo-300 border border-zinc-700 rounded transition"
                  >
                    {testingKey === "apollo" ? "Testing..." : "Test Connection"}
                  </button>
                </div>

                <div>
                  <input
                    type="password"
                    value={form.APOLLO_API_KEY}
                    onChange={(e) => setForm({ ...form, APOLLO_API_KEY: e.target.value })}
                    placeholder="apollo_api_key_••••••••"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                  />
                </div>

                {testResults.apollo && (
                  <div className={`text-xs p-2 rounded ${testResults.apollo.status === "CONNECTED" ? "bg-emerald-950/60 text-emerald-300" : "bg-rose-950/60 text-rose-300"}`}>
                    {testResults.apollo.message}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: OUTBOUND SMTP */}
          {activeTab === "smtp" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <span>📤</span> Outbound Email (SMTP)
                  </h2>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Transports personalized HTML campaigns, calibration reports, and quotation follow-ups.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-1 text-xs font-semibold rounded-full border ${form.OUTBOUND_TEST_MODE ? "bg-amber-950 text-amber-300 border-amber-700" : "bg-emerald-950 text-emerald-300 border-emerald-700"}`}>
                    {form.OUTBOUND_TEST_MODE ? "🛡️ TEST MODE (Safe)" : "🚀 LIVE MASS DISPATCH"}
                  </span>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm text-zinc-200">SMTP Server Configuration</span>
                  <button
                    type="button"
                    disabled={testingKey === "smtp"}
                    onClick={() => runTest("smtp")}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-indigo-300 border border-zinc-700 rounded transition"
                  >
                    {testingKey === "smtp" ? "Testing..." : "Test SMTP Connection"}
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="md:col-span-2">
                    <label className="block text-xs text-zinc-400 mb-1">SMTP Host</label>
                    <input
                      type="text"
                      value={form.SMTP_HOST}
                      onChange={(e) => setForm({ ...form, SMTP_HOST: e.target.value })}
                      placeholder="smtp.gmail.com or mail.oorja.local"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Port</label>
                    <input
                      type="number"
                      value={form.SMTP_PORT}
                      onChange={(e) => setForm({ ...form, SMTP_PORT: parseInt(e.target.value) || 587 })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Username / Mailbox Email</label>
                    <input
                      type="text"
                      value={form.SMTP_USER}
                      onChange={(e) => setForm({ ...form, SMTP_USER: e.target.value })}
                      placeholder="sales@oorja.local"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Password</label>
                    <input
                      type="password"
                      value={form.SMTP_PASSWORD}
                      onChange={(e) => setForm({ ...form, SMTP_PASSWORD: e.target.value })}
                      placeholder="••••••••"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Sender From Name</label>
                    <input
                      type="text"
                      value={form.SMTP_FROM_NAME}
                      onChange={(e) => setForm({ ...form, SMTP_FROM_NAME: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Sender From Email</label>
                    <input
                      type="text"
                      value={form.SMTP_FROM_EMAIL}
                      onChange={(e) => setForm({ ...form, SMTP_FROM_EMAIL: e.target.value })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-6 pt-2">
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.SMTP_USE_TLS}
                      onChange={(e) => setForm({ ...form, SMTP_USE_TLS: e.target.checked })}
                      className="rounded bg-zinc-900 border-zinc-700 text-indigo-600 focus:ring-0"
                    />
                    Use TLS (Port 587 Recommended)
                  </label>
                  <label className="flex items-center gap-2 text-xs text-zinc-300 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.OUTBOUND_TEST_MODE}
                      onChange={(e) => setForm({ ...form, OUTBOUND_TEST_MODE: e.target.checked })}
                      className="rounded bg-zinc-900 border-zinc-700 text-indigo-600 focus:ring-0"
                    />
                    Keep Safe Test Mode Active (Logs to Console/Mailhog)
                  </label>
                </div>

                {testResults.smtp && (
                  <div className={`text-xs p-2 rounded ${testResults.smtp.status === "CONNECTED" ? "bg-emerald-950/60 text-emerald-300" : "bg-rose-950/60 text-rose-300"}`}>
                    {testResults.smtp.message}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: INBOUND IMAP */}
          {activeTab === "imap" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <span>📥</span> Inbound Email (IMAP)
                  </h2>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Monitors customer replies, procurement inquiries, and objection signals.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={copySMTPToIMAP}
                  className="px-2.5 py-1 text-xs bg-indigo-950 text-indigo-300 border border-indigo-800 hover:bg-indigo-900 rounded transition"
                >
                  🔗 Copy Credentials from SMTP
                </button>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-sm text-zinc-200">IMAP Mailbox Connection</span>
                  <button
                    type="button"
                    disabled={testingKey === "imap"}
                    onClick={() => runTest("imap")}
                    className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-indigo-300 border border-zinc-700 rounded transition"
                  >
                    {testingKey === "imap" ? "Testing..." : "Test IMAP Connection"}
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="md:col-span-2">
                    <label className="block text-xs text-zinc-400 mb-1">IMAP Host</label>
                    <input
                      type="text"
                      value={form.IMAP_HOST}
                      onChange={(e) => setForm({ ...form, IMAP_HOST: e.target.value })}
                      placeholder="imap.gmail.com or mail.oorja.local"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Port</label>
                    <input
                      type="number"
                      value={form.IMAP_PORT}
                      onChange={(e) => setForm({ ...form, IMAP_PORT: parseInt(e.target.value) || 993 })}
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Username / Mailbox Email</label>
                    <input
                      type="text"
                      value={form.IMAP_USER}
                      onChange={(e) => setForm({ ...form, IMAP_USER: e.target.value })}
                      placeholder="sales@oorja.local"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-zinc-400 mb-1">Password</label>
                    <input
                      type="password"
                      value={form.IMAP_PASSWORD}
                      onChange={(e) => setForm({ ...form, IMAP_PASSWORD: e.target.value })}
                      placeholder="••••••••"
                      className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>
                </div>

                {testResults.imap && (
                  <div className={`text-xs p-2 rounded ${testResults.imap.status === "CONNECTED" ? "bg-emerald-950/60 text-emerald-300" : "bg-rose-950/60 text-rose-300"}`}>
                    {testResults.imap.message}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 5: WEB & RESEARCH */}
          {activeTab === "research" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span>🌐</span> Web & Regulatory Research Scrapers
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Powers the Regulatory Radar, corporate press release scanner, and NABL directory lookups.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-4">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Serper Google Search API Key</label>
                  <input
                    type="password"
                    value={form.SERPER_API_KEY}
                    onChange={(e) => setForm({ ...form, SERPER_API_KEY: e.target.value })}
                    placeholder="serper_key_••••••••"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Apify Actor API Token</label>
                  <input
                    type="password"
                    value={form.APIFY_API_TOKEN}
                    onChange={(e) => setForm({ ...form, APIFY_API_TOKEN: e.target.value })}
                    placeholder="apify_api_••••••••"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none font-mono"
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: CALLING */}
          {activeTab === "calling" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span>📞</span> Calling & Voice Agent Pilot
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Controlled voice agent for pre-call briefs and live pilot call verification.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-4">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Pilot Phone Number (Operator Test Device)</label>
                  <input
                    type="text"
                    value={form.PILOT_PHONE_NUMBER}
                    onChange={(e) => setForm({ ...form, PILOT_PHONE_NUMBER: e.target.value })}
                    placeholder="+91-9876543210"
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-200 focus:border-indigo-500 outline-none"
                  />
                  <p className="text-xs text-zinc-500 mt-1">
                    Used during Stage 12 of the live pilot for end-to-end voice script validation.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 7: SECURITY */}
          {activeTab === "security" && (
            <div className="space-y-6">
              <div className="border-b border-zinc-800 pb-3">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span>🔒</span> Secret Storage & Zero-Trust Architecture
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  How Salesoorja protects sensitive API keys and credentials.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-zinc-950/40 border border-zinc-800 space-y-3 text-xs text-zinc-300 leading-relaxed">
                <div className="flex items-center gap-2 text-indigo-400 font-semibold">
                  <span>🛡️</span> Zero Plaintext Secret Exposure
                </div>
                <p>
                  API keys and passwords are encrypted and persisted strictly in the backend. When querying settings from the frontend, values are masked with <code>••••••••</code>.
                </p>
                <div className="flex items-center gap-2 text-indigo-400 font-semibold pt-2">
                  <span>⚡</span> Dynamic Runtime Overrides
                </div>
                <p>
                  Any updates made through this interface immediately take effect across the AI Orchestrator, Apollo Adapter, and SMTP Dispatcher without requiring container restarts.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
