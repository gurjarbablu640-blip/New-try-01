import React, { useEffect, useState } from "react";
import api from "../api";

export default function CampaignEngine() {
  const [campaigns, setCampaigns] = useState([]);
  const [name, setName] = useState("");
  const [channel, setChannel] = useState("email");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const response = await api.get("/campaigns");
      setCampaigns(response.data.results || []);
      setError("");
    } catch (e) {
      setError(e?.response?.data?.detail || "Campaign data could not be loaded.");
    }
  };

  useEffect(() => { load(); }, []);

  const createCampaign = async () => {
    if (!name.trim()) return;
    setBusy(true);
    try {
      await api.post("/campaigns", {
        name: name.trim(),
        channel,
        daily_limit: 50,
      });
      setName("");
      await load();
    } catch (e) {
      setError(e?.response?.data?.detail || "Campaign creation failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4 rounded-2xl border bg-white p-5 shadow-sm">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Campaign Engine</h2>
        <p className="text-sm text-gray-500">
          Build controlled outbound sequences. Approval is required before any future sender can execute them.
        </p>
      </div>

      <div className="flex flex-col gap-2 md:flex-row">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Campaign name"
          className="flex-1 rounded-lg border px-3 py-2 text-sm"
        />
        <select value={channel} onChange={(e) => setChannel(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="email">Email</option>
          <option value="whatsapp">WhatsApp</option>
          <option value="linkedin">LinkedIn</option>
        </select>
        <button
          onClick={createCampaign}
          disabled={busy || !name.trim()}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Creating..." : "Create draft"}
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {campaigns.length === 0 ? (
        <div className="rounded-xl border bg-gray-50 p-4 text-sm text-gray-500">No campaigns created yet.</div>
      ) : (
        <div className="space-y-2">
          {campaigns.map((campaign) => (
            <div key={campaign.id} className="rounded-xl border p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <div className="font-medium text-gray-900">{campaign.name}</div>
                  <div className="text-xs text-gray-500">
                    {campaign.channel} · {campaign.step_count} steps · {campaign.recipient_count} recipients
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-600">{campaign.status}</span>
                  <span className={`rounded-full px-2 py-1 text-xs ${campaign.approved ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                    {campaign.approved ? "Approved" : "Approval required"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
