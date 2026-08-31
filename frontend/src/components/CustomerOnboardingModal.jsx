import React, { useState } from "react";
import { onboardManualProspect } from "../api";

const INSTRUMENT_OPTIONS = [
  "Dimensional (Vernier, Micrometer, CMM, Height Gauge)",
  "Pressure (Vacuum, Hydraulic, Differential Gauges)",
  "Thermal (Thermocouple, RTD, Temperature Chambers)",
  "Electrical (Multimeter, Insulation Tester, Power Meter)",
  "Mass & Volume (Weighing Balance, Micro-pipette)",
  "Torque & Force (Torque Wrenches, Load Cells)",
];

export default function CustomerOnboardingModal({ isOpen, onClose, onCustomerCreated }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createdResult, setCreatedResult] = useState(null);

  const [formData, setFormData] = useState({
    company_name: "",
    industry: "",
    city: "",
    state: "",
    country: "India",
    facility: "",
    website: "",
    contact_name: "",
    contact_role: "",
    contact_email: "",
    contact_phone: "",
    existing_vendor: "",
    calibration_requirement: "",
    instrument_categories: [],
    last_calibration_date: "",
    next_calibration_due: "",
    notes: "",
  });

  if (!isOpen) return null;

  const toggleInstrument = (inst) => {
    setFormData((prev) => {
      const exists = prev.instrument_categories.includes(inst);
      return {
        ...prev,
        instrument_categories: exists
          ? prev.instrument_categories.filter((i) => i !== inst)
          : [...prev.instrument_categories, inst],
      };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.company_name.trim()) {
      setError("Company Name is required.");
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const res = await onboardManualProspect({
        ...formData,
        instrument_categories: formData.instrument_categories.map((c) => c.split(" ")[0]),
        last_calibration_date: formData.last_calibration_date || null,
        next_calibration_due: formData.next_calibration_due || null,
      });
      setCreatedResult(res.data);
      if (onCustomerCreated) onCustomerCreated(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setCreatedResult(null);
    setError(null);
    setFormData({
      company_name: "",
      industry: "",
      city: "",
      state: "",
      country: "India",
      facility: "",
      website: "",
      contact_name: "",
      contact_role: "",
      contact_email: "",
      contact_phone: "",
      existing_vendor: "",
      calibration_requirement: "",
      instrument_categories: [],
      last_calibration_date: "",
      next_calibration_due: "",
      notes: "",
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl max-w-2xl w-full shadow-2xl overflow-hidden my-8 text-zinc-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/60">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2">
              <span>🏢</span> Manual Prospect Onboarding
            </h3>
            <p className="text-xs text-zinc-400 mt-0.5">
              Enter customer details to instantly seed CRM, CompanyBrain, Belief State, and Calibration Inference.
            </p>
          </div>
          <button
            onClick={handleReset}
            className="text-zinc-400 hover:text-white text-lg px-2 py-1 rounded transition"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 max-h-[75vh] overflow-y-auto space-y-6">
          {error && (
            <div className="p-3 bg-rose-950/80 border border-rose-800 text-rose-200 text-xs rounded-lg">
              {error}
            </div>
          )}

          {createdResult ? (
            /* Guided Workflow Step */
            <div className="space-y-6">
              <div className="p-4 bg-emerald-950/60 border border-emerald-800 rounded-lg">
                <h4 className="text-sm font-bold text-emerald-300 flex items-center gap-2">
                  <span>✓</span> Account Onboarded Successfully
                </h4>
                <p className="text-xs text-emerald-200/80 mt-1">
                  <strong>{createdResult.company.name}</strong> has been created with initial calibration need score{" "}
                  <strong>{Math.round(createdResult.initial_calibration_need * 100)}%</strong> and recommended initial action{" "}
                  <code className="bg-emerald-900 px-1 py-0.5 rounded text-emerald-200">{createdResult.initial_decision}</code>.
                </p>
              </div>

              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-3">
                  Guided Next-Best-Action Workflow
                </h5>
                <div className="space-y-2">
                  {createdResult.guided_workflow.map((step) => (
                    <div
                      key={step.step}
                      className="p-3 bg-zinc-950/60 border border-zinc-800 rounded-lg flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-3">
                        <span className="w-5 h-5 rounded-full bg-indigo-900 text-indigo-300 font-bold flex items-center justify-center text-[10px]">
                          {step.step}
                        </span>
                        <span className="font-semibold text-zinc-200">{step.label}</span>
                      </div>
                      <span className="text-[10px] text-zinc-500 font-mono">{step.action}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2 border-t border-zinc-800">
                <button
                  onClick={handleReset}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition"
                >
                  Done & Close
                </button>
              </div>
            </div>
          ) : (
            /* Input Form */
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Section 1: Company Info */}
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                  1. Company & Plant Profile
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="md:col-span-2">
                    <label className="block text-xs text-zinc-300 mb-1">
                      Company Name <span className="text-rose-400">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.company_name}
                      onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                      placeholder="e.g. Tata Motors Transmission Division"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Industry</label>
                    <input
                      type="text"
                      value={formData.industry}
                      onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                      placeholder="e.g. Automotive Tier-1, Pharma"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Facility / Plant Unit</label>
                    <input
                      type="text"
                      value={formData.facility}
                      onChange={(e) => setFormData({ ...formData, facility: e.target.value })}
                      placeholder="e.g. Pune Chakan Plant 2"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">City</label>
                    <input
                      type="text"
                      value={formData.city}
                      onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                      placeholder="e.g. Pune"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Website</label>
                    <input
                      type="text"
                      value={formData.website}
                      onChange={(e) => setFormData({ ...formData, website: e.target.value })}
                      placeholder="e.g. tatamotors.com"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Section 2: Key Contact */}
              <div className="pt-2 border-t border-zinc-800">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                  2. Decision Maker / Key Contact
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Contact Full Name</label>
                    <input
                      type="text"
                      value={formData.contact_name}
                      onChange={(e) => setFormData({ ...formData, contact_name: e.target.value })}
                      placeholder="e.g. Mr. Rajesh Sharma"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Designation / Role</label>
                    <input
                      type="text"
                      value={formData.contact_role}
                      onChange={(e) => setFormData({ ...formData, contact_role: e.target.value })}
                      placeholder="e.g. Head of QA & Metrology"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Email</label>
                    <input
                      type="email"
                      value={formData.contact_email}
                      onChange={(e) => setFormData({ ...formData, contact_email: e.target.value })}
                      placeholder="e.g. rsharma@tatamotors.com"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Phone</label>
                    <input
                      type="text"
                      value={formData.contact_phone}
                      onChange={(e) => setFormData({ ...formData, contact_phone: e.target.value })}
                      placeholder="e.g. +91 9820011223"
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Section 3: Metrology & Calibration Scope */}
              <div className="pt-2 border-t border-zinc-800">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                  3. Calibration Scope & Equipment
                </h4>
                <div className="space-y-3">
                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Instrument Categories</label>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {INSTRUMENT_OPTIONS.map((inst) => {
                        const selected = formData.instrument_categories.includes(inst);
                        return (
                          <button
                            type="button"
                            key={inst}
                            onClick={() => toggleInstrument(inst)}
                            className={`p-2 rounded text-left text-xs border transition flex items-center justify-between ${
                              selected
                                ? "bg-indigo-950/80 border-indigo-500 text-indigo-200"
                                : "bg-zinc-950/40 border-zinc-800 text-zinc-400 hover:border-zinc-700"
                            }`}
                          >
                            <span>{inst}</span>
                            <span>{selected ? "✓" : "+"}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-zinc-300 mb-1">Existing Calibration Vendor</label>
                      <input
                        type="text"
                        value={formData.existing_vendor}
                        onChange={(e) => setFormData({ ...formData, existing_vendor: e.target.value })}
                        placeholder="e.g. Intertek / Local NABL Lab"
                        className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                      />
                    </div>

                    <div>
                      <label className="block text-xs text-zinc-300 mb-1">Next Calibration Due Date</label>
                      <input
                        type="date"
                        value={formData.next_calibration_due}
                        onChange={(e) => setFormData({ ...formData, next_calibration_due: e.target.value })}
                        className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs text-zinc-300 mb-1">Specific Requirements / Notes</label>
                    <textarea
                      rows={2}
                      value={formData.notes}
                      onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                      placeholder="e.g. Expansion of line with 4 new CNC machining centers; tight ISO 17025 audit requirement."
                      className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-1.5 text-sm text-zinc-100 focus:border-indigo-500 outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Submit Buttons */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={handleReset}
                  className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-semibold rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition flex items-center gap-2 shadow"
                >
                  {loading ? "Onboarding..." : "✨ Onboard & Seed Intelligence"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
