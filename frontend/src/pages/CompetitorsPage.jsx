import React, { useState, useEffect } from "react";
import {
  ShieldAlert,
  Plus,
  Flame,
  CheckCircle2,
  RefreshCw,
  Zap,
  Target,
  Award,
  AlertTriangle,
  Building,
  Upload,
  Search,
  FileText,
  Layers,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import {
  getLabScopes,
  getLabScopeDetails,
  importLabScope,
  uploadScopeDocument,
  searchLabParameters,
  compareLabScopes,
  getCompetitorObservations,
  createCompetitorObservation,
  getCompanies,
} from "../api";

const PAN_INDIA_REGIONS = [
  "PAN INDIA",
  "Maharashtra",
  "Gujarat",
  "Tamil Nadu",
  "Karnataka",
  "Telangana",
  "Delhi NCR",
  "Rajasthan",
  "Uttar Pradesh",
  "Madhya Pradesh",
  "West Bengal",
];

const DISCIPLINES = [
  "All",
  "Mechanical",
  "Thermal",
  "Electro-Technical",
  "Fluid Flow",
  "Optical",
  "Medical Devices",
];

export default function CompetitorsPage() {
  const [activeTab, setActiveTab] = useState("scopes"); // scopes, search, compare, observations
  const [labScopes, setLabScopes] = useState([]);
  const [selectedLab, setSelectedLab] = useState(null);
  const [selectedLabDetails, setSelectedLabDetails] = useState(null);
  const [observations, setObservations] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [notification, setNotification] = useState("");

  // Filters
  const [selectedState, setSelectedState] = useState("PAN INDIA");
  const [selectedDiscipline, setSelectedDiscipline] = useState("All");

  // Parameter Search state
  const [paramQuery, setParamQuery] = useState("");
  const [paramSearchResults, setParamSearchResults] = useState([]);
  const [searchingParams, setSearchingParams] = useState(false);

  // Compare state
  const [compareLab1, setCompareLab1] = useState("");
  const [compareLab2, setCompareLab2] = useState("");
  const [comparisonData, setComparisonData] = useState(null);
  const [comparing, setComparing] = useState(false);

  // Upload / Import Modal
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadLabName, setUploadLabName] = useState("");
  const [uploadState, setUploadState] = useState("Maharashtra");
  const [uploadPreview, setUploadPreview] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  // Observation Modal
  const [showObsModal, setShowObsModal] = useState(false);
  const [newObs, setNewObs] = useState({
    company_id: "",
    competitor_name: "",
    observation_type: "Pricing",
    title: "Client shared competitor NABL scope quote",
    evidence: "",
    classification: "WEB_EVIDENCE",
  });

  const loadInitialData = async () => {
    setLoading(true);
    try {
      const [scopesRes, obsRes, coRes] = await Promise.allSettled([
        getLabScopes({
          state: selectedState === "PAN INDIA" ? undefined : selectedState,
          discipline: selectedDiscipline === "All" ? undefined : selectedDiscipline,
          limit: 100,
        }),
        getCompetitorObservations({ limit: 50 }),
        getCompanies({ limit: 100 }),
      ]);

      if (scopesRes.status === "fulfilled") {
        const list = scopesRes.value.data?.results || [];
        setLabScopes(list);
        if (list.length > 0) {
          loadLabDetails(list[0].id);
        } else {
          setSelectedLab(null);
          setSelectedLabDetails(null);
        }
      }
      if (obsRes.status === "fulfilled") {
        setObservations(obsRes.value.data?.results || []);
      }
      if (coRes.status === "fulfilled") {
        setCompanies(coRes.value.data?.results || []);
      }
    } catch (err) {
      console.error("Lab scopes load error:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadLabDetails = async (labId) => {
    try {
      const res = await getLabScopeDetails(labId);
      setSelectedLabDetails(res.data);
      setSelectedLab(labScopes.find((l) => l.id === labId) || res.data);
    } catch (err) {
      console.error("Lab details error:", err);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, [selectedState, selectedDiscipline]);

  const handleParseDocument = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;
    setUploadLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      const res = await uploadScopeDocument(formData, {
        lab_name: uploadLabName,
        state: uploadState,
      });
      setUploadPreview(res.data?.preview);
    } catch (err) {
      setNotification("Failed to parse scope document.");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleConfirmImport = async () => {
    if (!uploadPreview) return;
    setUploadLoading(true);
    try {
      const res = await importLabScope({
        lab_name: uploadPreview.lab_name,
        certificate_no: uploadPreview.certificate_no,
        accreditation_standard: uploadPreview.accreditation_standard,
        validity_date: uploadPreview.validity_date,
        state: uploadPreview.state,
        city: uploadPreview.city,
        source_file: uploadPreview.source_file,
        source_reference: uploadPreview.source_reference,
        parameters: uploadPreview.parameters,
      });
      setNotification(`Imported NABL Lab Scope: ${res.data?.lab_name} with ${res.data?.parameters_indexed} parameters!`);
      setShowUploadModal(false);
      setUploadPreview(null);
      setUploadFile(null);
      loadInitialData();
    } catch (err) {
      setNotification("Failed to import lab scope record.");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleSearchParameters = async (e) => {
    e.preventDefault();
    if (!paramQuery.trim()) return;
    setSearchingParams(true);
    try {
      const res = await searchLabParameters({
        q: paramQuery,
        discipline: selectedDiscipline,
        state: selectedState,
      });
      setParamSearchResults(res.data?.results || []);
    } catch (err) {
      setNotification("Search failed.");
    } finally {
      setSearchingParams(false);
    }
  };

  const handleRunComparison = async (e) => {
    e.preventDefault();
    if (!compareLab1 || !compareLab2) return;
    setComparing(true);
    try {
      const res = await compareLabScopes({
        lab1_id: compareLab1,
        lab2_id: compareLab2,
      });
      setComparisonData(res.data);
    } catch (err) {
      setNotification("Comparison failed.");
    } finally {
      setComparing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">NABL Lab Scope & Competitor Intelligence</h1>
            <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
              PAN-INDIA SCOPE REPOSITORY
            </span>
          </div>
          <p className="text-sm text-dark-muted">
            Official NABL accredited laboratory schedules, parameter-level capability overlaps, and evidence-backed competitor observations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowUploadModal(true)}
            className="flex items-center gap-1.5 rounded-lg border border-brand-cyan/40 bg-brand-cyan/10 px-3 py-1.5 text-xs font-semibold text-brand-cyan hover:bg-brand-cyan/20 transition"
          >
            <Upload className="h-3.5 w-3.5" />
            <span>Upload NABL Lab Scope (PDF/CSV)</span>
          </button>
          <button
            onClick={() => setShowObsModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Log Field Observation</span>
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div className="rounded-xl border border-brand-emerald/30 bg-brand-emerald/10 px-4 py-3 text-xs text-brand-emerald flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Sub-Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-dark-border pb-2">
        <button
          onClick={() => setActiveTab("scopes")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
            activeTab === "scopes" ? "bg-brand-primary text-white" : "text-dark-muted hover:text-white hover:bg-dark-card"
          }`}
        >
          Accredited Laboratories ({labScopes.length})
        </button>
        <button
          onClick={() => setActiveTab("search")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
            activeTab === "search" ? "bg-brand-primary text-white" : "text-dark-muted hover:text-white hover:bg-dark-card"
          }`}
        >
          Parameter Capability Search
        </button>
        <button
          onClick={() => setActiveTab("compare")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
            activeTab === "compare" ? "bg-brand-primary text-white" : "text-dark-muted hover:text-white hover:bg-dark-card"
          }`}
        >
          Scope Overlap Comparator
        </button>
        <button
          onClick={() => setActiveTab("observations")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
            activeTab === "observations" ? "bg-brand-primary text-white" : "text-dark-muted hover:text-white hover:bg-dark-card"
          }`}
        >
          Field Observations ({observations.length})
        </button>
      </div>

      {/* TAB 1: ACCREDITED LABORATORIES DIRECTORY */}
      {activeTab === "scopes" && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-3 bg-dark-card p-3 rounded-xl border border-dark-border">
            <div className="flex items-center gap-2 text-xs text-dark-muted">
              <span>Region:</span>
              <select
                value={selectedState}
                onChange={(e) => setSelectedState(e.target.value)}
                className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-white font-medium"
              >
                {PAN_INDIA_REGIONS.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2 text-xs text-dark-muted">
              <span>Discipline:</span>
              <select
                value={selectedDiscipline}
                onChange={(e) => setSelectedDiscipline(e.target.value)}
                className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-white font-medium"
              >
                {DISCIPLINES.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 h-[calc(100vh-280px)]">
            {/* Left Column: Lab Directory */}
            <div className="dark-card p-3 lg:col-span-4 flex flex-col space-y-2 overflow-y-auto">
              <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider text-dark-muted">
                NABL Laboratories ({labScopes.length})
              </div>

              {labScopes.length === 0 ? (
                <div className="p-8 text-center text-xs text-dark-muted">
                  No NABL lab scopes found matching selected region. Click "Upload NABL Lab Scope" to add new accreditation schedules.
                </div>
              ) : (
                labScopes.map((lab) => {
                  const isSelected = selectedLab?.id === lab.id;
                  return (
                    <div
                      key={lab.id}
                      onClick={() => loadLabDetails(lab.id)}
                      className={`cursor-pointer rounded-xl p-3.5 text-xs transition border ${
                        isSelected
                          ? "bg-brand-primary/15 border-brand-primary/40 shadow-sm"
                          : "border-dark-border bg-dark-card hover:bg-dark-hover"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white text-sm">{lab.lab_name}</span>
                        <span className="rounded bg-brand-cyan/15 px-2 py-0.5 text-[10px] font-mono text-brand-cyan border border-brand-cyan/30">
                          {lab.state || "Pan-India"}
                        </span>
                      </div>

                      <div className="mt-1 text-dark-muted text-[11px]">
                        Certificate: <span className="text-white font-mono">{lab.certificate_no}</span>
                      </div>

                      <div className="mt-1 text-[11px] text-brand-emerald">
                        {lab.parameters_count} accredited parameters indexed
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column: Parameter Schedule */}
            <div className="dark-card p-5 lg:col-span-8 flex flex-col overflow-y-auto space-y-4">
              {!selectedLabDetails ? (
                <div className="flex h-full items-center justify-center text-xs text-dark-muted">
                  Select a laboratory from the directory to inspect its granular NABL parameter schedule.
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between pb-3 border-b border-dark-border">
                    <div>
                      <div className="flex items-center gap-3">
                        <h2 className="text-xl font-bold text-white">{selectedLabDetails.lab_name}</h2>
                        <span className="badge-primary rounded px-2 py-0.5 text-xs font-mono">
                          {selectedLabDetails.certificate_no}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-dark-muted">
                        Standard: <span className="text-white font-medium">{selectedLabDetails.accreditation_standard}</span> | Location: <span className="text-white font-medium">{selectedLabDetails.city ? `${selectedLabDetails.city}, ` : ""}{selectedLabDetails.state}</span> | Validity: <span className="text-brand-amber font-medium">{selectedLabDetails.validity_date}</span>
                      </div>
                    </div>
                  </div>

                  {/* Parameter List */}
                  <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted mb-2">
                      Accredited Measurement Capabilities ({selectedLabDetails.parameters?.length || 0})
                    </div>

                    <div className="border border-dark-border rounded-xl overflow-hidden divide-y divide-dark-border">
                      {selectedLabDetails.parameters?.map((p) => (
                        <div key={p.id} className="p-3 bg-dark-panel hover:bg-dark-card transition flex items-center justify-between text-xs">
                          <div>
                            <div className="font-semibold text-white">{p.parameter_name}</div>
                            <div className="text-[11px] text-dark-muted mt-0.5">
                              {p.discipline} • Range: <span className="text-white">{p.range_description}</span>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="font-mono text-brand-emerald text-xs font-semibold">
                              CMC: {p.cmc_uncertainty}
                            </div>
                            <div className="text-[10px] text-dark-muted font-mono mt-0.5">
                              Source Page {p.source_page || 1}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: PARAMETER CAPABILITY SEARCH */}
      {activeTab === "search" && (
        <div className="space-y-4">
          <form onSubmit={handleSearchParameters} className="flex gap-3 bg-dark-card p-4 rounded-xl border border-dark-border">
            <div className="flex-1 relative">
              <Search className="h-4 w-4 absolute left-3 top-3 text-dark-muted" />
              <input
                type="text"
                value={paramQuery}
                onChange={(e) => setParamQuery(e.target.value)}
                placeholder="Search instrument or parameter (e.g. micrometer, cmm, pressure transmitter, RTD)..."
                className="w-full rounded-lg border border-dark-border bg-dark-bg pl-9 pr-4 py-2 text-sm text-white"
              />
            </div>
            <button
              type="submit"
              disabled={searchingParams || !paramQuery.trim()}
              className="rounded-lg bg-brand-primary px-4 py-2 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50"
            >
              {searchingParams ? "Searching..." : "Search Capabilities"}
            </button>
          </form>

          <div className="dark-card p-4 space-y-3">
            <div className="text-xs font-semibold uppercase tracking-wider text-dark-muted">
              Search Results ({paramSearchResults.length} accredited laboratories capable)
            </div>

            {paramSearchResults.length === 0 ? (
              <div className="py-12 text-center text-xs text-dark-muted">
                Enter an instrument or parameter name to query accredited laboratories across Pan-India.
              </div>
            ) : (
              <div className="divide-y divide-dark-border border border-dark-border rounded-xl overflow-hidden">
                {paramSearchResults.map((res) => (
                  <div key={res.parameter_id} className="p-4 bg-dark-panel hover:bg-dark-card transition flex items-center justify-between text-xs">
                    <div>
                      <div className="font-bold text-white text-sm">{res.lab_name}</div>
                      <div className="text-xs text-brand-cyan mt-1">{res.parameter_name} ({res.discipline})</div>
                      <div className="text-[11px] text-dark-muted mt-0.5">Range: {res.range_description} • Location: {res.state}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-brand-emerald text-xs font-bold">CMC: {res.cmc_uncertainty}</div>
                      <div className="text-[10px] text-dark-muted font-mono mt-1">Cert: {res.certificate_no} • Page {res.source_page}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: SCOPE OVERLAP COMPARATOR */}
      {activeTab === "compare" && (
        <div className="space-y-4">
          <form onSubmit={handleRunComparison} className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-dark-card p-4 rounded-xl border border-dark-border items-end">
            <div>
              <label className="block text-dark-muted text-xs mb-1 font-medium">Laboratory 1 (Baseline / Oorja)</label>
              <select
                value={compareLab1}
                onChange={(e) => setCompareLab1(e.target.value)}
                className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-xs text-white"
              >
                <option value="">Select Lab...</option>
                {labScopes.map((l) => (
                  <option key={l.id} value={l.id}>{l.lab_name} ({l.certificate_no})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-dark-muted text-xs mb-1 font-medium">Laboratory 2 (Competitor Lab)</label>
              <select
                value={compareLab2}
                onChange={(e) => setCompareLab2(e.target.value)}
                className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-xs text-white"
              >
                <option value="">Select Lab...</option>
                {labScopes.map((l) => (
                  <option key={l.id} value={l.id}>{l.lab_name} ({l.certificate_no})</option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              disabled={comparing || !compareLab1 || !compareLab2}
              className="rounded-lg bg-brand-primary px-4 py-2 text-xs font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50 h-9"
            >
              {comparing ? "Comparing Scopes..." : "Compare Scopes"}
            </button>
          </form>

          {comparisonData && (
            <div className="space-y-4">
              {/* Metrics Strip */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div className="dark-card p-4 text-center">
                  <div className="text-dark-muted text-xs">Common Overlapping Scopes</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-brand-cyan">{comparisonData.metrics?.common_parameters_count}</div>
                </div>
                <div className="dark-card p-4 text-center">
                  <div className="text-dark-muted text-xs">{comparisonData.lab1?.name} Unique</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-brand-emerald">{comparisonData.metrics?.lab1_unique_count}</div>
                </div>
                <div className="dark-card p-4 text-center">
                  <div className="text-dark-muted text-xs">{comparisonData.lab2?.name} Unique</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-brand-amber">{comparisonData.metrics?.lab2_unique_count}</div>
                </div>
                <div className="dark-card p-4 text-center">
                  <div className="text-dark-muted text-xs">Scope Overlap %</div>
                  <div className="mt-1 font-mono text-2xl font-bold text-white">{comparisonData.metrics?.overlap_percentage}%</div>
                </div>
              </div>

              {/* Overlapping Parameters Table */}
              <div className="dark-card p-5 space-y-3">
                <h3 className="text-sm font-bold text-white uppercase">Factual Overlapping Scope Parameters</h3>
                <div className="divide-y divide-dark-border border border-dark-border rounded-xl overflow-hidden">
                  {comparisonData.common_parameters?.map((p, idx) => (
                    <div key={idx} className="p-3 bg-dark-panel flex items-center justify-between text-xs">
                      <div className="font-semibold text-white">{p.parameter}</div>
                      <div className="text-right text-dark-muted text-[11px]">
                        <span>Lab 1: {p.lab1_range} (CMC: {p.lab1_cmc})</span>
                        <span className="mx-2">•</span>
                        <span>Lab 2: {p.lab2_range} (CMC: {p.lab2_cmc})</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: FIELD OBSERVATIONS */}
      {activeTab === "observations" && (
        <div className="dark-card p-5 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-dark-border">
            <h2 className="font-semibold text-white text-base">Verified Field Observations ({observations.length})</h2>
            <span className="rounded bg-brand-primary/20 border border-brand-primary/40 px-2 py-0.5 text-[10px] font-mono text-brand-cyan">
              SOURCE TRACEABLE
            </span>
          </div>

          <div className="space-y-3">
            {observations.length === 0 ? (
              <div className="py-8 text-center text-xs text-dark-muted">
                No competitor field observations logged yet. Click "Log Field Observation" above.
              </div>
            ) : (
              observations.map((obs) => (
                <div key={obs.id} className="rounded-xl border border-dark-border bg-dark-card p-4 text-xs space-y-1">
                  <div className="flex items-center justify-between font-semibold text-white">
                    <span className="text-sm">{obs.title}</span>
                    <span className="font-mono text-dark-muted text-[10px]">{obs.observed_at?.slice(0, 10)}</span>
                  </div>
                  <div className="text-dark-muted leading-relaxed">{obs.evidence}</div>
                  <div className="pt-2 flex items-center gap-2">
                    <span className="rounded bg-brand-cyan/15 px-2 py-0.5 text-[10px] font-mono text-brand-cyan border border-brand-cyan/30">
                      {obs.classification || "FIELD_OBSERVATION"}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* UPLOAD / IMPORT NABL LAB SCOPE MODAL */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-dark-border pb-3">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Upload className="h-5 w-5 text-brand-cyan" />
                  <span>Import NABL Lab Accreditation Scope</span>
                </h2>
                <p className="text-xs text-dark-muted">
                  Upload official NABL certificate / scope schedule (PDF, CSV, TXT) to index into the Pan-India repository.
                </p>
              </div>
              <button onClick={() => { setShowUploadModal(false); setUploadPreview(null); }} className="text-dark-muted hover:text-white">✕</button>
            </div>

            {!uploadPreview ? (
              <form onSubmit={handleParseDocument} className="space-y-4 text-xs">
                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Laboratory Name</label>
                  <input
                    type="text"
                    value={uploadLabName}
                    onChange={(e) => setUploadLabName(e.target.value)}
                    placeholder="e.g. TCR Engineering Services or Micro Calibration Systems"
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  />
                </div>

                <div>
                  <label className="block text-dark-muted mb-1 font-medium">Operating State / Region</label>
                  <select
                    value={uploadState}
                    onChange={(e) => setUploadState(e.target.value)}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                  >
                    {PAN_INDIA_REGIONS.filter((r) => r !== "PAN INDIA").map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-dark-muted mb-1 font-medium">NABL Scope File (PDF / CSV / TXT)</label>
                  <input
                    type="file"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:bg-brand-primary file:text-white hover:file:bg-brand-primaryHover"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-dark-border">
                  <button
                    type="button"
                    onClick={() => setShowUploadModal(false)}
                    className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={uploadLoading || !uploadFile}
                    className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow disabled:opacity-50"
                  >
                    {uploadLoading ? "Extracting Parameters..." : "Parse & Review"}
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4 text-xs">
                <div className="rounded-xl border border-brand-emerald/30 bg-brand-emerald/10 p-3 text-brand-emerald">
                  <div className="font-bold text-sm">Extracted Lab: {uploadPreview.lab_name}</div>
                  <div className="text-xs text-white/90 mt-1">Certificate: {uploadPreview.certificate_no} | Region: {uploadPreview.state}</div>
                </div>

                <div className="border border-dark-border rounded-xl overflow-hidden">
                  <div className="bg-dark-card px-3 py-2 font-semibold text-white border-b border-dark-border">
                    Extracted Scope Parameters ({uploadPreview.parameters?.length || 0})
                  </div>
                  <div className="max-h-48 overflow-y-auto divide-y divide-dark-border">
                    {uploadPreview.parameters?.map((p, idx) => (
                      <div key={idx} className="p-3 flex items-center justify-between">
                        <div>
                          <div className="font-medium text-white">{p.parameter_name}</div>
                          <div className="text-[11px] text-dark-muted">{p.discipline} • Range: {p.range_description}</div>
                        </div>
                        <div className="text-right font-mono font-bold text-brand-emerald">
                          CMC: {p.cmc_uncertainty}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-dark-border">
                  <button
                    type="button"
                    onClick={() => setUploadPreview(null)}
                    className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmImport}
                    disabled={uploadLoading}
                    className="rounded-lg bg-brand-emerald px-4 py-2 font-semibold text-dark-bg hover:opacity-90 shadow"
                  >
                    {uploadLoading ? "Saving..." : "Confirm & Ingest Scope Schedule"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* LOG FIELD OBSERVATION MODAL */}
      {showObsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-dark-border bg-dark-panel p-6 shadow-2xl animate-in zoom-in-95 space-y-4">
            <h2 className="text-lg font-bold text-white mb-2">Log Competitor Field Observation</h2>
            <form onSubmit={async (e) => {
              e.preventDefault();
              if (!newObs.title || !newObs.evidence) return;
              try {
                await createCompetitorObservation({
                  company_id: newObs.company_id ? Number(newObs.company_id) : null,
                  competitor_id: null,
                  observation_type: newObs.observation_type,
                  title: newObs.title,
                  evidence: newObs.evidence,
                  classification: newObs.classification,
                });
                setShowObsModal(false);
                setNotification("Field observation recorded with provenance.");
                loadInitialData();
              } catch (err) {
                setNotification("Failed to record observation.");
              }
            }} className="space-y-4 text-xs">
              <div>
                <label className="block text-dark-muted mb-1 font-medium">Customer Account (Optional)</label>
                <select
                  value={newObs.company_id}
                  onChange={(e) => setNewObs({ ...newObs, company_id: e.target.value })}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                >
                  <option value="">Select Account...</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Observation Title</label>
                <input
                  type="text"
                  value={newObs.title}
                  onChange={(e) => setNewObs({ ...newObs, title: e.target.value })}
                  required
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Evidence / Field Details</label>
                <textarea
                  value={newObs.evidence}
                  onChange={(e) => setNewObs({ ...newObs, evidence: e.target.value })}
                  required
                  rows={3}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-dark-muted mb-1 font-medium">Provenance Classification</label>
                <select
                  value={newObs.classification}
                  onChange={(e) => setNewObs({ ...newObs, classification: e.target.value })}
                  className="w-full rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-white"
                >
                  <option value="WEB_EVIDENCE">WEB_EVIDENCE (Public RFP, website quote)</option>
                  <option value="VERIFIED_FACT">VERIFIED_FACT (Physical customer certificate/quote)</option>
                  <option value="AI_INFERENCE">AI_INFERENCE (Statistical correlation)</option>
                  <option value="USER_CORRECTED_KNOWLEDGE">USER_CORRECTED_KNOWLEDGE (Sales rep feedback)</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-dark-border">
                <button
                  type="button"
                  onClick={() => setShowObsModal(false)}
                  className="rounded-lg border border-dark-border bg-dark-bg px-3 py-2 text-dark-muted hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-primary px-4 py-2 font-semibold text-white hover:bg-brand-primaryHover shadow"
                >
                  Save Observation
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
