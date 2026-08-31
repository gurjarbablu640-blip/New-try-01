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
  BrainCircuit,
  Compass,
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
        "### 1. ANSWER\nWelcome to **Ask Oorja Deep Reasoning Studio**. I am your sales intelligence copilot operating across Pan-India industrial corridors with direct access to NABL 300-lab scope schedules, customer plant assets, calibration due windows, quotation price history, and second-order trigger discovery.\n\n### 2. WHY\nMetrology sales decisions require strict factual grounding, explicit uncertainty estimation, and zero hallucination.\n\n### 8. RECOMMENDED ACTION\nSelect an inquiry below or type a query regarding Pan-India target accounts, asset calibration schedules, or competitive scope overlaps.",
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
        content: "### 1. ANSWER\nError communicating with Oorja Assistant API. Please ensure the backend container is running.\n\n### 6. WHAT WE DON'T KNOW\nBackend service connection status is currently offline.",
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const promptChips = [
    "Who should I contact today across Pan-India industrial corridors?",
    "Which customer assets are due for calibration within 30 days?",
    "Can we calibrate 0-100 bar pressure gauges and what is our CMC?",
    "What is our verified scope advantage against regional testing labs?",
    "Recommend optimal pricing for CMM 3D inspection based on price history",
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">Ask Oorja AI Studio</h1>
            <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
              8-PART DEEP REASONING
            </span>
          </div>
          <p className="text-sm text-dark-muted">
            Structured 8-part evidence-backed answers with strict factual separation of verified data vs hypotheses.
          </p>
        </div>
      </div>

      {/* Main Chat Container */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-220px)]">
        {/* Chat Feed (8 cols) */}
        <div className="dark-card p-4 lg:col-span-8 flex flex-col justify-between h-full">
          {/* Scrollable Message History */}
          <div className="space-y-4 overflow-y-auto pr-2 flex-1">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex gap-3 text-xs leading-relaxed ${
                  m.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {m.role === "assistant" && (
                  <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-brand-primary/20 text-brand-cyan border border-brand-primary/30">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div
                  className={`max-w-[88%] rounded-2xl p-4 shadow-sm space-y-2 ${
                    m.role === "user"
                      ? "bg-brand-primary text-white font-medium"
                      : "bg-dark-panel text-white border border-dark-border"
                  }`}
                >
                  <div className="whitespace-pre-wrap font-sans text-xs leading-relaxed">
                    {m.content}
                  </div>

                  {m.toolUsed && (
                    <div className="mt-2 pt-2 border-t border-dark-border flex items-center justify-between text-[10px] text-dark-muted font-mono">
                      <span>Tool Invoked: <span className="text-brand-cyan">{m.toolUsed}</span></span>
                      {m.intent && <span>Intent: {m.intent}</span>}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-3 text-xs items-center text-dark-muted animate-pulse">
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-brand-primary/20 text-brand-cyan">
                  <BrainCircuit className="h-4 w-4 animate-spin" />
                </div>
                <span>Synthesizing 8-part reasoning chain from database & NABL schedules...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Prompt Chips */}
          <div className="pt-3 pb-2 flex gap-1.5 overflow-x-auto no-scrollbar">
            {promptChips.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => handleSendMessage(chip)}
                disabled={loading}
                className="flex-shrink-0 rounded-full border border-dark-border bg-dark-bg px-3 py-1 text-[11px] text-dark-muted hover:text-white hover:border-brand-primary transition"
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Chat Input Bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex gap-2 pt-2 border-t border-dark-border"
          >
            <input
              type="text"
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              placeholder="Ask anything (e.g. Which plant assets are overdue for calibration?)..."
              disabled={loading}
              className="flex-1 rounded-xl border border-dark-border bg-dark-bg px-4 py-2.5 text-xs text-white placeholder-dark-muted focus:border-brand-primary focus:outline-none"
            />
            <button
              type="submit"
              disabled={loading || !inputPrompt.trim()}
              className="rounded-xl bg-brand-primary px-4 py-2.5 text-white hover:bg-brand-primaryHover shadow disabled:opacity-50 transition flex items-center justify-center"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>

        {/* Right Sidebar: Active Tools & Capabilities (4 cols) */}
        <div className="dark-card p-4 lg:col-span-4 flex flex-col space-y-4 overflow-y-auto">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Compass className="h-4 w-4 text-brand-cyan" />
              <span>Standard 8-Part Reasoning Protocol</span>
            </h3>
            <p className="text-xs text-dark-muted mt-1">
              Every answer is deterministically verified and segmented:
            </p>
          </div>

          <div className="space-y-2 text-[11px]">
            {[
              { num: "1", title: "ANSWER", desc: "Direct, unambiguous response" },
              { num: "2", title: "WHY", desc: "Underlying business causality" },
              { num: "3", title: "EVIDENCE", desc: "Database & certificate references" },
              { num: "4", title: "WHAT WE KNOW", desc: "Verified local database facts" },
              { num: "5", title: "WHAT WE INFER", desc: "Second-order hypotheses with probability" },
              { num: "6", title: "WHAT WE DON'T KNOW", desc: "Gaps & research required" },
              { num: "7", title: "CONFIDENCE", desc: "Calibrated percentage & rationale" },
              { num: "8", title: "RECOMMENDED ACTION", desc: "Concrete next sales step" },
            ].map((s) => (
              <div key={s.num} className="p-2 rounded-lg bg-dark-panel border border-dark-border flex items-start gap-2">
                <span className="font-mono font-bold text-brand-cyan text-[10px] bg-brand-primary/20 rounded px-1.5 py-0.5">
                  {s.num}
                </span>
                <div>
                  <span className="font-semibold text-white">{s.title}</span>
                  <p className="text-dark-muted text-[10px]">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
