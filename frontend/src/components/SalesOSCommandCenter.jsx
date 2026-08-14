import React, { useEffect, useState } from "react";
import api from "../api";

const cards = [
  ["Open opportunities", "open_opportunities"],
  ["Active tasks", "active_tasks"],
  ["Open quotations", "open_quotations"],
];

export default function SalesOSCommandCenter() {
  const [summary, setSummary] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [quotations, setQuotations] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const [summaryResponse, tasksResponse, quotationsResponse] = await Promise.all([
        api.get("/sales-os/summary"),
        api.get("/sales-os/tasks?status=Open&limit=5"),
        api.get("/sales-os/quotations?status=Draft"),
      ]);
      setSummary(summaryResponse.data);
      setTasks(tasksResponse.data.results || []);
      setQuotations((quotationsResponse.data.results || []).slice(0, 5));
    } catch (err) {
      setError(err?.response?.data?.detail || "Sales OS data could not be loaded.");
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <section className="space-y-4 rounded-2xl border bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Oorja Sales OS</h2>
          <p className="text-sm text-gray-500">
            Operating view for opportunities, tasks and quotation approvals.
          </p>
        </div>
        <button
          onClick={load}
          className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {cards.map(([label, key]) => (
          <div key={key} className="rounded-xl border bg-gray-50 p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</div>
            <div className="mt-2 text-2xl font-bold text-gray-900">{summary?.[key] ?? "—"}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Priority tasks</h3>
            <span className="text-xs text-gray-500">Open</span>
          </div>
          {tasks.length === 0 ? (
            <p className="text-sm text-gray-500">No open Sales OS tasks.</p>
          ) : (
            <div className="space-y-2">
              {tasks.map((task) => (
                <div key={task.id} className="rounded-lg border px-3 py-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-gray-900">{task.title}</div>
                      {task.ai_reason && (
                        <div className="mt-1 text-xs text-gray-500">{task.ai_reason}</div>
                      )}
                    </div>
                    <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-600">
                      {task.priority}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Quotation approval queue</h3>
            <span className="text-xs text-amber-600">Human approval</span>
          </div>
          {quotations.length === 0 ? (
            <p className="text-sm text-gray-500">No draft quotations waiting for approval.</p>
          ) : (
            <div className="space-y-2">
              {quotations.map((quotation) => (
                <div key={quotation.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                  <div>
                    <div className="text-sm font-medium text-gray-900">
                      {quotation.quotation_number || `Quotation #${quotation.id}`}
                    </div>
                    <div className="text-xs text-gray-500">{quotation.customer_name}</div>
                  </div>
                  <span className="text-sm font-semibold text-gray-800">
                    ₹{Number(quotation.total || 0).toLocaleString("en-IN")}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
