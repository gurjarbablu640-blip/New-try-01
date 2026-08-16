import React, { useState, useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Bot,
  Send,
  Sparkles,
  RefreshCw,
  Building,
  Gauge,
  Calendar,
  ShieldCheck,
  Zap,
  CheckCircle2,
  FileText,
} from "lucide-react";
import { askOorjaAI, getAssistantTools } from "../api";

export default function AssistantPage() {
  const { onOpenCompany } = useOutletContext();
  const chatEndRef = useRef(null);

  const [messages, setMessages] = useState([
    {
      id: "intro",
      role: "assistant",
      content:
        "Welcome to **Ask Oorja AI Studio**. I am your private Sales OS copilot with direct access to our NABL metrology catalog, customer plant assets, calibration due windows, quotation engine, and Gujarat industrial corridors.\n\nHow can I accelerate your sales pipeline today?",
      intent: "general_greeting",
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [tools, setTools] = useState([]);

  useEffect(() => {
    const loadTools = async () => {
      try {
        const res = await getAssistantTools();
        setTools(res.data?.tools || []);
      } catch (err) {
        console.error("Tools load error:", err);
      }
    };
    loadTools();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSendMessage = async (textToSend) => {
    const text = textToSend || inputPrompt;
    if (!text.trim()) return;

    const userMsg = { id: Date.now().toString(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    if (!textToSend) setInputPrompt("");
    setLoading(true);

    try {
      const res = await askOorjaAI(text);
      const botMsg = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: res.data?.answer || "No response generated.",
        intent: res.data?.intent,
        toolUsed: res.data?.tool_used,
        data: res.data?.data,
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      const errMsg = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Error communicating with Oorja Assistant API. Please ensure the backend container is running.",
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const promptChips = [
    "Who should I contact today in Gujarat chemical estates?",
    "Which customer assets are due for calibration within 30 days?",
    "Plan a 1-day sales trip itinerary for Dahej PCPIR",
    "What is our winning pitch against TCR Engineering?",
    "Is Bourdon pressure gauge 0-100 bar within Oorja's NABL scope?",
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Ask Oorja AI Studio</h1>
          <p className="text-sm text-dark-muted">
            Deterministic AI orchestrator with 12 typed metrology sales tools and real-time CRM bindings.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-full border border-brand-cyan/30 bg-brand-cyan/10 px-3 py-1 text-xs font-medium text-brand-cyan">
            <Zap className="h-3 w-3" />
            <span>12 Typed Tools Connected</span>
          </span>
        </div>
      </div>

      {/* Dual Pane AI Studio Layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-220px)]">
        {/* MAIN CHAT AREA (8 cols) */}
        <div className="dark-card flex flex-col lg:col-span-8 h-full overflow-hidden">
          {/* Quick Prompt Chips */}
          <div className="flex gap-2 overflow-x-auto p-3 border-b border-dark-border bg-dark-panel">
            {promptChips.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(chip)}
                className="flex-shrink-0 rounded-lg border border-dark-border bg-dark-bg px-3 py-1 text-[11px] text-dark-muted hover:border-brand-primary hover:text-white transition"
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Chat Messages Stream */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((m) => {
              const isBot = m.role === "assistant";

              return (
                <div key={m.id} className={`flex gap-3 ${isBot ? "items-start" : "items-start justify-end"}`}>
                  {isBot && (
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-tr from-brand-primary to-brand-cyan text-white shadow flex-shrink-0">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed ${
                      isBot
                        ? "border border-dark-border bg-dark-card text-white shadow-sm"
                        : "bg-brand-primary text-white font-medium shadow-md"
                    }`}
                  >
                    {isBot && m.intent && (
                      <div className="mb-2 flex items-center gap-2">
                        <span className="rounded bg-brand-cyan/15 px-2 py-0.5 text-[10px] font-mono font-semibold text-brand-cyan border border-brand-cyan/30">
                          Intent: {m.intent}
                        </span>
                      </div>
                    )}

                    <div className="whitespace-pre-line font-sans">{m.content}</div>
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="flex items-center gap-3 text-xs text-dark-muted">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-primary/20 text-brand-cyan">
                  <Bot className="h-4 w-4 animate-pulse" />
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-3 w-3 animate-spin rounded-full border-2 border-brand-primary border-t-transparent"></div>
                  <span>Executing deterministic metrology sales tool...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Prompt Input Form */}
          <div className="p-4 border-t border-dark-border bg-dark-panel">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendMessage();
              }}
              className="flex items-center gap-3"
            >
              <input
                type="text"
                value={inputPrompt}
                onChange={(e) => setInputPrompt(e.target.value)}
                placeholder="Ask Oorja: 'Which plants in Dahej need calibration follow-up?'..."
                disabled={loading}
                className="flex-1 rounded-xl border border-dark-border bg-dark-bg px-4 py-2.5 text-xs text-white placeholder-dark-muted focus:border-brand-primary focus:outline-none"
              />
              <button
                type="submit"
                disabled={loading || !inputPrompt.trim()}
                className="flex items-center gap-1.5 rounded-xl bg-brand-primary px-4 py-2.5 text-xs font-bold text-white shadow hover:bg-brand-primaryHover transition disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" />
                <span>Send</span>
              </button>
            </form>
          </div>
        </div>

        {/* RIGHT CONTEXT PANEL: Available Tools & Knowledge (4 cols) */}
        <div className="dark-card p-4 lg:col-span-4 h-full flex flex-col space-y-4 overflow-y-auto">
          <div>
            <h2 className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
              Connected Deterministic Tools ({tools.length || 12})
            </h2>
            <div className="space-y-1.5">
              {[
                { name: "get_priority_outreach", desc: "Accounts ready for campaign outreach" },
                { name: "get_calibration_due", desc: "Customer instruments due in 30/60 days" },
                { name: "check_nabl_fit", desc: "Parameter scope & calibration feasibility" },
                { name: "get_territory_clusters", desc: "Industrial corridor density & urgency" },
                { name: "get_visit_recommendations", desc: "Optimized multi-stop plant visit itineraries" },
                { name: "get_competitor_intel", desc: "Regional Gujarat battlecards & counter-pitches" },
                { name: "get_company_facts", desc: "Account 360 overview & buying signals" },
                { name: "draft_outreach_message", desc: "Contextual email sequence copy generation" },
              ].map((t, idx) => (
                <div key={idx} className="rounded-lg border border-dark-border bg-dark-bg p-2.5 text-xs">
                  <div className="font-mono font-semibold text-brand-cyan">{t.name}</div>
                  <div className="text-[11px] text-dark-muted mt-0.5">{t.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
