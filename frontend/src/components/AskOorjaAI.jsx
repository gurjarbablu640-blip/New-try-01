import React, { useState } from "react";
import api from "../api";

const examples = [
  "Show me all Gujarat automotive leads",
  "Find contacts for QA managers",
  "Find quotations for Tata",
  "Give me the current sales summary",
];

export default function AskOorjaAI() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const classify = (text) => {
    const q = text.toLowerCase();
    if (q.includes("summary") || q.includes("pipeline") || q.includes("sales")) return { tool: "sales_summary" };
    if (q.includes("quotation") || q.includes("quote")) return { tool: "search_quotations", query: text };
    if (q.includes("contact") || q.includes("manager") || q.includes("person")) return { tool: "search_contacts", query: text };
    return { tool: "search_companies", query: text };
  };

  const ask = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await api.post("/assistant/tool", classify(question));
      if (response.data.error) throw new Error(response.data.error);
      setResult(response.data);
    } catch (err) {
      setError(err?.response?.data?.detail || err.message || "Unable to answer right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-2xl border bg-white p-5 shadow-sm space-y-4">
      <div>
        <h2 className="text-xl font-bold text-gray-900">Ask Oorja AI</h2>
        <p className="text-sm text-gray-500">Ask about CRM data using bounded, auditable tools.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {examples.map((example) => (
          <button
            key={example}
            onClick={() => setQuestion(example)}
            className="rounded-full border px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
          >
            {example}
          </button>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="Ask something about your sales data..."
          className="flex-1 rounded-lg border px-3 py-2 text-sm"
        />
        <button
          onClick={ask}
          disabled={loading || !question.trim()}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {result && (
        <div className="rounded-xl border bg-gray-50 p-4">
          <div className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-500">Tool result · {result.tool}</div>

          {result.tool === "sales_summary" ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <div><div className="text-xs text-gray-500">Open opportunities</div><div className="text-lg font-bold">{result.open_opportunities}</div></div>
              <div><div className="text-xs text-gray-500">Pipeline value</div><div className="text-lg font-bold">₹{Number(result.open_pipeline_value || 0).toLocaleString("en-IN")}</div></div>
              <div><div className="text-xs text-gray-500">Open tasks</div><div className="text-lg font-bold">{result.open_tasks}</div></div>
              <div><div className="text-xs text-gray-500">Open quotations</div><div className="text-lg font-bold">{result.open_quotations}</div></div>
            </div>
          ) : (
            <div className="space-y-2">
              {(result.results || []).length === 0 ? (
                <p className="text-sm text-gray-500">No matching records found.</p>
              ) : (
                (result.results || []).map((item) => (
                  <div key={item.id || item.chunk_id || item.quotation_item_id} className="rounded-lg border bg-white p-3">
                    <div className="font-medium text-gray-900">{item.name || item.customer_name || item.instrument_name || item.title}</div>
                    <div className="mt-1 text-xs text-gray-500">
                      {item.designation || item.designation === "" ? item.designation : item.industry || item.quotation_number || item.company || ""}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
