import React, { useState, useEffect } from "react";
import {
  getCompanies,
  getCompanyBrain,
  getCalibrationInference,
  getLeadScorecard,
  getRegulatoryRadar,
  getResearchBrief,
  generateRolePitch,
  getNextBestAction,
  getWhitespaceMap,
  getCallBrief,
  analyzeCall,
  getMLDataset,
  addCompanyFact,
  addTimelineEvent,
  discoverSignal,
  reasonSignalCausality,
  evaluateCadenceNonResponse,
  composeHtmlEmail,
  executeApolloPilot,
  getCompanyBeliefState,
  updateCompanyBelief,
  getDecisionPolicy,
  getCBRSimilarCases,
  getCausalTemplates,
} from "../api";
import CustomerOnboardingModal from "../components/CustomerOnboardingModal";

export default function IntelligencePage() {
  const [activeTab, setActiveTab] = useState("brain");
  const [companies, setCompanies] = useState([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [loading, setLoading] = useState(false);
  const [showOnboardingModal, setShowOnboardingModal] = useState(false);

  // Tab Data States
  const [brainData, setBrainData] = useState(null);
  const [inferenceData, setInferenceData] = useState(null);
  const [scorecardData, setScorecardData] = useState(null);
  const [radarData, setRadarData] = useState(null);
  const [briefData, setBriefData] = useState(null);
  const [pitchRole, setPitchRole] = useState("Quality / Metrology");
  const [generatedPitch, setGeneratedPitch] = useState(null);
  const [actionData, setActionData] = useState(null);
  const [whitespaceData, setWhitespaceData] = useState(null);
  const [callBriefData, setCallBriefData] = useState(null);
  const [transcriptInput, setTranscriptInput] = useState(
    "Sales: Good morning Rajesh sir, calling from Oorja Technical Services regarding your CMM calibration.\nCustomer: We already have a calibration vendor, but our annual calibration is due next month.\nSales: Understood sir. Are there any parameters where turnaround is causing a production issue?\nCustomer: Can you send your NABL scope and rate card?"
  );
  const [callAnalysisResult, setCallAnalysisResult] = useState(null);
  const [mlDatasetData, setMLDatasetData] = useState(null);

  // Reasoning Foundation State
  const [beliefStateData, setBeliefStateData] = useState(null);
  const [decisionPolicyData, setDecisionPolicyData] = useState(null);
  const [cbrCasesData, setCbrCasesData] = useState(null);
  const [newEvidenceEpistemic, setNewEvidenceEpistemic] = useState("FACT");
  const [newEvidenceSignal, setNewEvidenceSignal] = useState("plant_expansion");
  const [newEvidenceTitle, setNewEvidenceTitle] = useState("Commissioned 8 High-Precision CNC Lines");
  const [newEvidenceDesc, setNewEvidenceDesc] = useState("Machining facility certified for ISO 9001 and IATF 16949 audit readiness.");
  const [newEvidenceSource, setNewEvidenceSource] = useState("Annual Report & BSE Filing");
  const [newEvidenceContra, setNewEvidenceContra] = useState("");

  // Signal Discovery State
  const [sigCompany, setSigCompany] = useState("Kirloskar Oil Engines Ltd");
  const [sigCity, setSigCity] = useState("Pune");
  const [sigIndustry, setSigIndustry] = useState("Heavy Engineering");
  const [sigType, setSigType] = useState("plant_expansion");
  const [sigTitle, setSigTitle] = useState("₹250 Cr High-Horsepower Engine Assembly Expansion");
  const [sigDesc, setSigDesc] = useState("Setting up new multi-axis CNC machining, dynamometer testing bays, and precision fuel injection calibration facility in Kagal.");
  const [signalReasoningResult, setSignalReasoningResult] = useState(null);
  const [signalIngestResult, setSignalIngestResult] = useState(null);

  // Cadence & HTML Studio State
  const [cadenceDays, setCadenceDays] = useState(15);
  const [cadenceRole, setCadenceRole] = useState("Purchase");
  const [cadenceResult, setCadenceResult] = useState(null);
  const [emailHtmlRole, setEmailHtmlRole] = useState("Quality");
  const [emailHtmlOutput, setEmailHtmlOutput] = useState(null);

  // Apollo Pilot State
  const [apolloOrgName, setApolloOrgName] = useState("Bharat Forge Ltd");
  const [apolloPilotResult, setApolloPilotResult] = useState(null);
  const [apolloLoading, setApolloLoading] = useState(false);

  // Quick Fact / Timeline Form
  const [newFactKey, setNewFactKey] = useState("");
  const [newFactCategory, setNewFactCategory] = useState("equipment");
  const [newFactEvidence, setNewFactEvidence] = useState("");
  const [newFactSource, setNewFactSource] = useState("website_scrape");

  useEffect(() => {
    loadCompanies();
    loadRegulatoryRadar();
    loadMLDataset();
  }, []);

  useEffect(() => {
    if (selectedCompanyId) {
      loadCompanyIntelligence(selectedCompanyId);
    }
  }, [selectedCompanyId]);

  const loadCompanies = async () => {
    try {
      const res = await getCompanies({ limit: 50 });
      const comps = res.data?.results || res.data || [];
      setCompanies(comps);
      if (comps.length > 0 && !selectedCompanyId) {
        setSelectedCompanyId(comps[0].id);
      }
    } catch (err) {
      console.error("Failed to load companies", err);
    }
  };

  const loadRegulatoryRadar = async () => {
    try {
      const res = await getRegulatoryRadar();
      setRadarData(res.data);
    } catch (err) {
      console.error("Failed to load regulatory radar", err);
    }
  };

  const loadMLDataset = async () => {
    try {
      const res = await getMLDataset();
      setMLDatasetData(res.data);
    } catch (err) {
      console.error("Failed to load ML dataset", err);
    }
  };

  const loadCompanyIntelligence = async (cid) => {
    setLoading(true);
    try {
      const [brainRes, inferRes, scoreRes, briefRes, actionRes, wsRes, cbRes, beliefRes, policyRes, cbrRes] = await Promise.allSettled([
        getCompanyBrain(cid),
        getCalibrationInference(cid),
        getLeadScorecard(cid),
        getResearchBrief(cid),
        getNextBestAction(cid),
        getWhitespaceMap(cid),
        getCallBrief(cid),
        getCompanyBeliefState(cid),
        getDecisionPolicy(cid),
        getCBRSimilarCases(cid),
      ]);

      if (brainRes.status === "fulfilled") setBrainData(brainRes.value.data);
      if (inferRes.status === "fulfilled") setInferenceData(inferRes.value.data);
      if (scoreRes.status === "fulfilled") setScorecardData(scoreRes.value.data);
      if (briefRes.status === "fulfilled") setBriefData(briefRes.value.data);
      if (actionRes.status === "fulfilled") setActionData(actionRes.value.data);
      if (wsRes.status === "fulfilled") setWhitespaceData(wsRes.value.data);
      if (cbRes.status === "fulfilled") setCallBriefData(cbRes.value.data);
      if (beliefRes.status === "fulfilled") setBeliefStateData(beliefRes.value.data);
      if (policyRes.status === "fulfilled") setDecisionPolicyData(policyRes.value.data);
      if (cbrRes.status === "fulfilled") setCbrCasesData(cbrRes.value.data);
    } catch (err) {
      console.error("Error loading intelligence", err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateBeliefWithEvidence = async (e) => {
    e.preventDefault();
    if (!selectedCompanyId || !newEvidenceTitle) return;
    try {
      await updateCompanyBelief({
        company_id: Number(selectedCompanyId),
        epistemic_type: newEvidenceEpistemic,
        signal_type: newEvidenceSignal,
        title: newEvidenceTitle,
        description: newEvidenceDesc,
        source: newEvidenceSource,
        source_reliability: 0.90,
        contradicting_statement: newEvidenceContra || null,
      });
      setNewEvidenceContra("");
      loadCompanyIntelligence(selectedCompanyId);
    } catch (err) {
      console.error("Failed to update belief state", err);
    }
  };

  const handleGeneratePitch = async () => {
    if (!selectedCompanyId) return;
    try {
      const res = await generateRolePitch({
        company_id: Number(selectedCompanyId),
        target_role: pitchRole,
      });
      setGeneratedPitch(res.data);
    } catch (err) {
      console.error("Failed to generate role pitch", err);
    }
  };

  const handleAnalyzeCall = async () => {
    try {
      const res = await analyzeCall({
        transcript_text: transcriptInput,
        company_id: selectedCompanyId ? Number(selectedCompanyId) : null,
      });
      setCallAnalysisResult(res.data);
    } catch (err) {
      console.error("Failed to analyze call", err);
    }
  };

  const handleAddFact = async (e) => {
    e.preventDefault();
    if (!selectedCompanyId || !newFactKey) return;
    try {
      await addCompanyFact(selectedCompanyId, {
        category: newFactCategory,
        fact_key: newFactKey,
        source: newFactSource,
        evidence_text: newFactEvidence,
        confidence: 0.9,
      });
      setNewFactKey("");
      setNewFactEvidence("");
      loadCompanyIntelligence(selectedCompanyId);
    } catch (err) {
      console.error("Failed to add fact", err);
    }
  };

  const handleReasonSignal = async () => {
    try {
      const res = await reasonSignalCausality({
        signal_type: sigType,
        raw_event_title: sigTitle,
        raw_event_description: sigDesc,
        company_name: sigCompany,
        industry: sigIndustry,
      });
      setSignalReasoningResult(res.data);
    } catch (err) {
      console.error("Failed to reason signal causality", err);
    }
  };

  const handleDiscoverSignal = async () => {
    try {
      const res = await discoverSignal({
        company_name: sigCompany,
        city: sigCity,
        industry: sigIndustry,
        signal_type: sigType,
        event_title: sigTitle,
        event_description: sigDesc,
      });
      setSignalIngestResult(res.data);
      loadCompanies();
    } catch (err) {
      console.error("Failed to discover lead via signal", err);
    }
  };

  const handleEvaluateCadence = async () => {
    if (!selectedCompanyId) return;
    try {
      const res = await evaluateCadenceNonResponse({
        company_id: Number(selectedCompanyId),
        days_since_outbound: Number(cadenceDays),
        non_response_threshold_days: 15,
        last_contacted_role: cadenceRole,
      });
      setCadenceResult(res.data);
    } catch (err) {
      console.error("Failed to evaluate cadence", err);
    }
  };

  const handleComposeHtmlEmail = async () => {
    const compName = brainData?.company_name || "Target Enterprise";
    try {
      const res = await composeHtmlEmail({
        company_name: compName,
        contact_name: "Sir/Madam",
        target_role: emailHtmlRole,
      });
      setEmailHtmlOutput(res.data);
    } catch (err) {
      console.error("Failed to render HTML email", err);
    }
  };

  const handleRunApolloPilot = async () => {
    setApolloLoading(true);
    try {
      const res = await executeApolloPilot({
        company_name: apolloOrgName,
        max_contacts: 5,
      });
      setApolloPilotResult(res.data);
    } catch (err) {
      console.error("Apollo pilot failed", err);
    } finally {
      setApolloLoading(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-white shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <div className="flex items-center gap-3">
            <span className="text-2xl">🧠</span>
            <h1 className="text-2xl font-bold tracking-tight">Salesoorja Decision Intelligence Hub</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              Master Learning Loop v3.0
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1">
            Predicts demand, reasons over business activity, infers hidden calibration requirements, and models decision structures.
          </p>
        </div>

        {/* Global Company Selector & Manual Prospect Entry */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowOnboardingModal(true)}
            className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow flex items-center gap-1.5 transition"
          >
            <span>+</span> Add Prospect Manually
          </button>

          <div className="flex items-center gap-3 bg-slate-800/80 p-2 rounded-lg border border-slate-700">
            <label className="text-xs text-slate-300 font-medium">Target Account:</label>
            <select
              value={selectedCompanyId}
              onChange={(e) => setSelectedCompanyId(e.target.value)}
              className="bg-slate-900 border border-slate-600 rounded px-3 py-1 text-sm text-white focus:ring-2 focus:ring-emerald-500"
            >
              {companies.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.city || "India"})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-700 space-x-1 overflow-x-auto pb-1">
        {[
          { id: "brain", label: "Company Brain & Timeline", icon: "🏢" },
          { id: "reasoning", label: "Reasoning Trace & Belief State", icon: "🧬" },
          { id: "signals", label: "Signal Radar & Causality", icon: "🛰️" },
          { id: "inference", label: "Calibration Need & Cost of Inaction", icon: "⚙️" },
          { id: "scoring", label: "Multi-Dimensional Scoring", icon: "🎯" },
          { id: "radar", label: "Regulatory Radar (5 Questions)", icon: "📡" },
          { id: "brief", label: "AI Research Brief & Campaigns", icon: "📋" },
          { id: "cadence", label: "Cadence & HTML Studio", icon: "✉️" },
          { id: "revenue", label: "Revenue Autopilot & Deal Rescue", icon: "⚡" },
          { id: "calling", label: "Call Intelligence & Playbook", icon: "📞" },
          { id: "mldataset", label: "Master ML Sales Dataset", icon: "📊" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2.5 rounded-t-lg font-medium text-sm transition-all flex items-center gap-2 whitespace-nowrap ${
              activeTab === tab.id
                ? "bg-slate-800 text-emerald-400 border-t-2 border-emerald-400 border-x border-slate-700"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Loading Indicator */}
      {loading && (
        <div className="text-center py-8 text-slate-400">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500 mb-2"></div>
          <p className="text-sm">Synthesizing intelligence dossier...</p>
        </div>
      )}

      {/* TAB 1: COMPANY BRAIN & TIMELINE */}
      {!loading && activeTab === "brain" && brainData && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Account Overview Card */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Account Identity</h2>
              <div className="mt-3">
                <p className="text-lg font-bold text-white">{brainData.company_name}</p>
                <p className="text-sm text-slate-400">{brainData.industry} • {brainData.location}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <span className="px-2.5 py-1 rounded text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                    ICP Score: {brainData.icp_score}/100
                  </span>
                  <span className="px-2.5 py-1 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                    Window: {brainData.buying_window || "Active"}
                  </span>
                  <span className="px-2.5 py-1 rounded text-xs font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                    Facts Logged: {brainData.facts_count}
                  </span>
                </div>
              </div>

              {/* Add Verifiable Fact Form */}
              <div className="mt-6 pt-5 border-t border-slate-800">
                <h3 className="text-xs font-semibold text-slate-300 uppercase">Record Verifiable Fact</h3>
                <form onSubmit={handleAddFact} className="mt-2 space-y-2">
                  <input
                    type="text"
                    placeholder="Fact Key (e.g. 5_axis_cnc_chakan)"
                    value={newFactKey}
                    onChange={(e) => setNewFactKey(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <select
                      value={newFactCategory}
                      onChange={(e) => setNewFactCategory(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                    >
                      <option value="equipment">Equipment</option>
                      <option value="process">Process</option>
                      <option value="certification">Certification</option>
                      <option value="expansion">Expansion</option>
                      <option value="vendor">Vendor</option>
                    </select>
                    <select
                      value={newFactSource}
                      onChange={(e) => setNewFactSource(e.target.value)}
                      className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                    >
                      <option value="website_scrape">Website</option>
                      <option value="apollo">Apollo</option>
                      <option value="crm_activity">CRM Activity</option>
                      <option value="quotation">Quotation</option>
                    </select>
                  </div>
                  <input
                    type="text"
                    placeholder="Evidence Text / Verbatim Quote"
                    value={newFactEvidence}
                    onChange={(e) => setNewFactEvidence(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-white"
                  />
                  <button
                    type="submit"
                    className="w-full py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium"
                  >
                    Save Fact with Provenance
                  </button>
                </form>
              </div>
            </div>

            {/* Stakeholder Decision Network */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow md:col-span-2">
              <div className="flex justify-between items-center mb-3">
                <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Stakeholder Decision Graph</h2>
                <span className="text-xs text-slate-400">Classified by Incentive Focus</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(brainData.stakeholder_network || []).map((s, idx) => (
                  <div key={idx} className="bg-slate-800/80 p-3.5 rounded-lg border border-slate-700/80">
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="text-sm font-semibold text-white">{s.name}</p>
                        <p className="text-xs text-emerald-400">{s.role}</p>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-700 text-slate-300 font-medium">
                        Inf: {s.influence_weight}/10
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-2">Dept: {s.department}</p>
                    <p className="text-xs text-amber-300/90 mt-1">Incentive: {s.incentive_focus || "Standard"}</p>
                    {s.email && <p className="text-xs text-blue-400 mt-1">✉️ {s.email}</p>}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Chronological Intelligence Timeline */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold mb-4">
              Company Intelligence Timeline (Internal + External Sequences)
            </h2>
            <div className="space-y-4 relative border-l-2 border-slate-800 ml-4 pl-6">
              {(brainData.timeline || []).map((ev, idx) => (
                <div key={idx} className="relative group">
                  <div className="absolute -left-[31px] top-1.5 w-3 h-3 rounded-full bg-emerald-500 border-2 border-slate-900"></div>
                  <div className="bg-slate-800/60 p-3.5 rounded-lg border border-slate-700/60">
                    <div className="flex flex-wrap justify-between items-center gap-2">
                      <span className="text-xs font-mono text-emerald-400">{ev.date}</span>
                      <span className="text-xs px-2 py-0.5 rounded font-medium bg-slate-700 text-slate-300">
                        {ev.event_type}
                      </span>
                      <span className="text-xs text-slate-400">Source: {ev.source}</span>
                    </div>
                    <p className="text-sm font-semibold text-white mt-1">{ev.title}</p>
                    {ev.description && <p className="text-xs text-slate-300 mt-1">{ev.description}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: CALIBRATION NEED & COST OF INACTION */}
      {!loading && activeTab === "inference" && inferenceData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Likely Parameters Inference */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow md:col-span-2 space-y-4">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">
              Equipment-to-Calibration Parameter Inference
            </h2>
            <p className="text-xs text-slate-400">
              Archetype: <span className="text-white font-medium">{inferenceData.inference?.inferred_industry_archetype}</span>. {inferenceData.inference?.reasoning}
            </p>
            <div className="space-y-3">
              {(inferenceData.inference?.parameter_inferences || []).map((param, idx) => (
                <div key={idx} className="bg-slate-800/70 p-3.5 rounded-lg border border-slate-700 flex justify-between items-center">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-white">{param.parameter} Calibration</p>
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        {(param.probability * 100).toFixed(0)}% Probability
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">
                      Likely Instruments: {param.likely_instruments.join(", ")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Instrument Population & Cost of Inaction */}
          <div className="space-y-6">
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Instrument Population (4 Tiers)</h2>
              <div className="mt-3 space-y-2">
                <div className="flex justify-between text-xs py-1 border-b border-slate-800">
                  <span className="text-slate-400">1. Known (CRM Verified):</span>
                  <span className="text-white font-bold">{inferenceData.instrument_population_estimate?.known_instruments_count}</span>
                </div>
                <div className="flex justify-between text-xs py-1 border-b border-slate-800">
                  <span className="text-slate-400">2. Estimated Total:</span>
                  <span className="text-emerald-400 font-bold">{inferenceData.instrument_population_estimate?.estimated_total_instruments}</span>
                </div>
                <div className="flex justify-between text-xs py-1 border-b border-slate-800">
                  <span className="text-slate-400">3. Est. Annual Market:</span>
                  <span className="text-amber-300 font-bold">₹{inferenceData.instrument_population_estimate?.estimated_annual_calibration_market_inr?.toLocaleString()}</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Cost of Inaction / Financial Exposure</h2>
              <div className="mt-3">
                <p className="text-2xl font-black text-rose-400">
                  ₹{inferenceData.cost_of_inaction?.total_estimated_exposure_inr?.toLocaleString()}
                </p>
                <p className="text-xs text-slate-400 mt-1">Potential business exposure from delayed / unaccredited calibration.</p>
                <div className="mt-4 p-3 bg-emerald-950/30 border border-emerald-800/40 rounded-lg">
                  <p className="text-xs text-emerald-300 font-medium">
                    {inferenceData.cost_of_inaction?.premium_justification?.value_statement}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: MULTI-DIMENSIONAL SCORING */}
      {!loading && activeTab === "scoring" && scorecardData && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4">
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Composite Score</p>
              <p className="text-3xl font-black text-emerald-400 mt-1">{scorecardData.composite_score}</p>
            </div>
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Buy Probability</p>
              <p className="text-2xl font-bold text-white mt-1">{(scorecardData.buy_probability * 100).toFixed(0)}%</p>
            </div>
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Price Sensitivity</p>
              <p className="text-xl font-bold text-amber-300 mt-1">{scorecardData.price_sensitivity}</p>
            </div>
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Premium Potential</p>
              <p className="text-xl font-bold text-purple-400 mt-1">{scorecardData.premium_potential}</p>
            </div>
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Buying Window</p>
              <p className="text-lg font-bold text-blue-400 mt-1">{scorecardData.buying_window}</p>
            </div>
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 text-center">
              <p className="text-xs text-slate-400 uppercase">Segment</p>
              <p className="text-xs font-bold text-emerald-300 mt-2">{scorecardData.strategic_segment}</p>
            </div>
          </div>

          {/* Granular Score Change Explanation */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold mb-3">
              Score Breakdown & Causal Explanations
            </h2>
            <div className="space-y-2">
              {(scorecardData.score_reasons || []).map((reason, idx) => (
                <div key={idx} className="flex justify-between items-center p-3 bg-slate-800/60 rounded-lg border border-slate-700/60">
                  <span className="text-sm text-slate-200">{reason.factor}</span>
                  <span className="font-mono font-bold text-emerald-400 px-2 py-0.5 bg-emerald-950/60 border border-emerald-800/60 rounded text-xs">
                    {reason.delta}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: REGULATORY RADAR (5 QUESTIONS) */}
      {!loading && activeTab === "radar" && radarData && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h2 className="text-base font-bold text-white">Active Regulatory Notices & 5-Question Commercial Impact</h2>
            <span className="text-xs text-emerald-400 font-mono">
              Total Active: {radarData.total_active_regulations}
            </span>
          </div>
          <div className="space-y-6">
            {(radarData.regulations || []).map((reg) => (
              <div key={reg.id} className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
                <div className="flex flex-wrap justify-between items-start gap-2">
                  <div>
                    <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      {reg.authority} • {reg.regulation_code}
                    </span>
                    <h3 className="text-base font-bold text-white mt-1.5">{reg.title}</h3>
                    <p className="text-xs text-slate-400 mt-1">{reg.summary}</p>
                  </div>
                  {reg.compliance_deadline && (
                    <div className="text-right">
                      <p className="text-xs text-slate-400">Compliance Deadline</p>
                      <p className="text-sm font-bold text-rose-400 font-mono">{reg.compliance_deadline}</p>
                    </div>
                  )}
                </div>

                {/* 5-Question Commercial Breakdown */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-3 border-t border-slate-800 text-xs">
                  <div className="bg-slate-800/60 p-3 rounded">
                    <span className="text-slate-400 font-semibold">1. What changed:</span>
                    <p className="text-slate-200 mt-0.5">{reg.commercial_impact_analysis?.what_changed}</p>
                  </div>
                  <div className="bg-slate-800/60 p-3 rounded">
                    <span className="text-slate-400 font-semibold">2. Affected Processes:</span>
                    <p className="text-slate-200 mt-0.5">{(reg.commercial_impact_analysis?.affected_processes || []).join(", ")}</p>
                  </div>
                  <div className="bg-slate-800/60 p-3 rounded">
                    <span className="text-slate-400 font-semibold">3. Calibration Requirement:</span>
                    <p className="text-slate-200 mt-0.5">{reg.commercial_impact_analysis?.calibration_requirement}</p>
                  </div>
                  <div className="bg-slate-800/60 p-3 rounded">
                    <span className="text-emerald-400 font-semibold">4. What Oorja Should Do (Opportunity):</span>
                    <p className="text-emerald-200 mt-0.5">{reg.commercial_impact_analysis?.sales_opportunity}</p>
                  </div>
                </div>

                {/* Matched Companies */}
                {reg.matched_companies && reg.matched_companies.length > 0 && (
                  <div className="pt-3 border-t border-slate-800">
                    <p className="text-xs font-semibold text-slate-300 mb-2">
                      Matched CRM Accounts ({reg.matched_companies_count} total):
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {reg.matched_companies.map((mc, idx) => (
                        <span key={idx} className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded text-xs text-white">
                          🏢 {mc.company_name} ({mc.urgency} Urgency)
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 5: AI RESEARCH BRIEF & ROLE-SPECIFIC CAMPAIGNS */}
      {!loading && activeTab === "brief" && briefData && (
        <div className="space-y-6">
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold mb-3">
              AI Lead Research Ticket: {briefData.company_name}
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h3 className="text-xs font-semibold text-emerald-400">Target Stakeholder Hierarchy</h3>
                <div className="mt-2 space-y-2">
                  {(briefData.target_stakeholders || []).map((sh, idx) => (
                    <div key={idx} className="p-2.5 bg-slate-800/70 rounded border border-slate-700 text-xs">
                      <p className="font-bold text-white">{sh.role}</p>
                      <p className="text-slate-300">{sh.title} ({sh.department})</p>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-xs font-semibold text-blue-400">Extraction Search Queries</h3>
                <div className="mt-2 space-y-1.5">
                  {(briefData.search_instructions?.google_queries || []).map((q, idx) => (
                    <div key={idx} className="p-2 bg-slate-800/50 rounded font-mono text-[11px] text-slate-300">
                      🔍 {q}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Role-Specific Pitch Generator */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
            <div className="flex flex-wrap justify-between items-center gap-3">
              <div>
                <h2 className="text-sm font-bold text-white">Role-Specific Campaign Pitch Generator</h2>
                <p className="text-xs text-slate-400">Tailors value propositions to Quality vs Purchase vs Maintenance vs Management.</p>
              </div>
              <div className="flex gap-2">
                <select
                  value={pitchRole}
                  onChange={(e) => setPitchRole(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded px-3 py-1 text-xs text-white"
                >
                  <option value="Quality / Metrology">Quality / Metrology (Traceability)</option>
                  <option value="Purchase / Procurement">Purchase / Procurement (Consolidation)</option>
                  <option value="Maintenance / Plant Head">Maintenance / Plant Head (Downtime)</option>
                  <option value="Management / CFO">Management / CFO (Risk & ROI)</option>
                </select>
                <button
                  onClick={handleGeneratePitch}
                  className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium"
                >
                  Generate Pitch
                </button>
              </div>
            </div>

            {generatedPitch && (
              <div className="p-4 bg-slate-800/80 rounded-lg border border-slate-700 space-y-2">
                <p className="text-xs text-slate-400 font-semibold">Subject:</p>
                <p className="text-sm font-bold text-white">{generatedPitch.subject}</p>
                <p className="text-xs text-slate-400 font-semibold mt-3">Personalized Body:</p>
                <pre className="text-xs text-slate-200 whitespace-pre-wrap font-sans bg-slate-900/60 p-3 rounded border border-slate-800">
                  {generatedPitch.body}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 6: REVENUE AUTOPILOT & DEAL RESCUE */}
      {!loading && activeTab === "revenue" && (
        <div className="space-y-6">
          {actionData && (
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
              <div className="flex justify-between items-center">
                <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Next Best Revenue Action</h2>
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  Priority: {actionData.priority}
                </span>
              </div>
              <div className="mt-3 p-4 bg-slate-800/80 rounded-lg border border-slate-700 space-y-2">
                <p className="text-base font-bold text-white">{actionData.recommended_action}</p>
                <div className="flex gap-4 text-xs text-slate-300">
                  <span>Channel: <strong className="text-emerald-400">{actionData.channel}</strong></span>
                  <span>Target: <strong className="text-blue-400">{actionData.target_role}</strong></span>
                </div>
                <p className="text-xs text-slate-400 mt-2">{actionData.reasoning}</p>
              </div>
            </div>
          )}

          {whitespaceData && (
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold mb-3">
                Account White-Space Map ({whitespaceData.expansion_opportunity_count} Unserved Expansion Opportunities)
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {Object.entries(whitespaceData.whitespace_map || {}).map(([param, info]) => (
                  <div
                    key={param}
                    className={`p-3.5 rounded-lg border text-xs ${
                      info.coverage === "Active"
                        ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                        : "bg-amber-950/40 border-amber-800/60 text-amber-300"
                    }`}
                  >
                    <p className="font-bold text-sm">{param}</p>
                    <p className="text-[11px] mt-1">{info.status}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 7: CALL INTELLIGENCE & OBJECTION PLAYBOOK */}
      {!loading && activeTab === "calling" && (
        <div className="space-y-6">
          {callBriefData && (
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-3">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">
                30-Second Pre-Call Brief for {callBriefData.contact_name} ({callBriefData.contact_role})
              </h2>
              <div className="p-3 bg-emerald-950/40 border border-emerald-800/50 rounded-lg text-xs">
                <span className="font-semibold text-emerald-400">Opening Script:</span>
                <p className="text-slate-200 mt-1 italic">"{callBriefData.opening_script}"</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <div className="p-3 bg-slate-800/70 rounded border border-slate-700">
                  <span className="font-semibold text-blue-400">Suggested Discovery Questions:</span>
                  <ul className="list-disc ml-4 mt-1 space-y-1 text-slate-300">
                    {(callBriefData.suggested_questions || []).map((q, idx) => (
                      <li key={idx}>{q}</li>
                    ))}
                  </ul>
                </div>
                <div className="p-3 bg-slate-800/70 rounded border border-slate-700">
                  <span className="font-semibold text-rose-400">Things NOT to Say:</span>
                  <p className="text-slate-300 mt-1">{callBriefData.things_to_avoid}</p>
                </div>
              </div>
            </div>
          )}

          {/* Transcript Analyzer */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-3">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Post-Call Transcript & Signal Analyzer</h2>
            <textarea
              rows={4}
              value={transcriptInput}
              onChange={(e) => setTranscriptInput(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded p-3 text-xs text-white font-mono"
            />
            <button
              onClick={handleAnalyzeCall}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-medium"
            >
              Analyze Transcript & Objections
            </button>

            {callAnalysisResult && (
              <div className="p-4 bg-slate-800/90 rounded-lg border border-slate-700 mt-4 space-y-3 text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-bold text-white">
                    Sales Call Score: <strong className="text-emerald-400">{callAnalysisResult.call_score}/100</strong>
                  </span>
                  <span className="text-slate-400">Next Action: {callAnalysisResult.recommended_next_action}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-700">
                  <div>
                    <span className="font-semibold text-emerald-400">Buying Signals Detected:</span>
                    <ul className="list-disc ml-4 mt-1 text-slate-300">
                      {callAnalysisResult.buying_signals_detected.map((s, idx) => (
                        <li key={idx}>{s}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <span className="font-semibold text-amber-400">Objections Detected:</span>
                    <ul className="list-disc ml-4 mt-1 text-slate-300">
                      {callAnalysisResult.objections_detected.map((o, idx) => (
                        <li key={idx}>{o}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 8: MASTER SALES ML DATASET */}
      {!loading && activeTab === "mldataset" && mlDatasetData && (
        <div className="space-y-6">
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow">
            <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Master Sales ML Feature Dataset</h2>
            <div className="mt-3 p-3 bg-slate-800/80 rounded border border-slate-700 text-xs flex justify-between items-center">
              <div>
                <p className="text-white font-medium">{mlDatasetData.status_message}</p>
                <p className="text-slate-400 mt-1">
                  Rows: {mlDatasetData.total_dataset_rows} • Won Conversions: {mlDatasetData.converted_outcomes} • Rate: {mlDatasetData.observed_conversion_rate}
                </p>
              </div>
              <span className={`px-2.5 py-1 rounded text-xs font-semibold ${
                mlDatasetData.dataset_ready_for_ml
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
              }`}>
                {mlDatasetData.dataset_ready_for_ml ? "ML Ready (XGBoost)" : "Heuristic + Rule Learning Mode"}
              </span>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300 border border-slate-800">
                <thead className="bg-slate-800 text-slate-400 uppercase text-[10px]">
                  <tr>
                    <th className="p-2">Company</th>
                    <th className="p-2">Industry</th>
                    <th className="p-2">ICP</th>
                    <th className="p-2">Expansion</th>
                    <th className="p-2">Overdue</th>
                    <th className="p-2">Quote INR</th>
                    <th className="p-2">Stakeholder</th>
                    <th className="p-2">Outcome</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {(mlDatasetData.records || []).slice(0, 10).map((r, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-2 font-medium text-white">{r.company_name}</td>
                      <td className="p-2">{r.industry}</td>
                      <td className="p-2">{r.icp_score}</td>
                      <td className="p-2">{r.has_expansion_signal ? "Yes" : "No"}</td>
                      <td className="p-2">{r.has_overdue_assets ? "Yes" : "No"}</td>
                      <td className="p-2">₹{r.quoted_amount_inr?.toLocaleString()}</td>
                      <td className="p-2">{r.primary_stakeholder_role}</td>
                      <td className="p-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          r.is_converted ? "bg-emerald-950 text-emerald-300" : "bg-slate-800 text-slate-400"
                        }`}>
                          {r.is_converted ? "Won" : "Open / Nurture"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 9: SIGNAL RADAR & BUSINESS CAUSALITY */}
      {!loading && activeTab === "signals" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Signal Input Form */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Signal Discovery Trigger</h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  Pre-RFQ Demand Sensor
                </span>
              </div>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-slate-400">Target Enterprise:</label>
                  <input
                    type="text"
                    value={sigCompany}
                    onChange={(e) => setSigCompany(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-slate-400">Location:</label>
                    <input
                      type="text"
                      value={sigCity}
                      onChange={(e) => setSigCity(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400">Industry Archetype:</label>
                    <input
                      type="text"
                      value={sigIndustry}
                      onChange={(e) => setSigIndustry(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-slate-400">Signal Classification:</label>
                  <select
                    value={sigType}
                    onChange={(e) => setSigType(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  >
                    <option value="plant_expansion">Greenfield / Brownfield Plant Expansion</option>
                    <option value="capex_announcement">Machinery CAPEX / CNC Commissioning</option>
                    <option value="qa_hiring">Quality / Metrology Engineer Hiring</option>
                    <option value="ev_battery_manufacturing">EV / High-Voltage Battery Transition</option>
                    <option value="regulatory_qco">BIS QCO / Legal Metrology Mandate</option>
                    <option value="iso_iatf_audit">IATF 16949 / ISO Audit Preparation</option>
                    <option value="tender_calibration">Public Calibration Tender / RFQ</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400">Event Title:</label>
                  <input
                    type="text"
                    value={sigTitle}
                    onChange={(e) => setSigTitle(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  />
                </div>
                <div>
                  <label className="text-slate-400">Event Raw Description / Context:</label>
                  <textarea
                    rows={3}
                    value={sigDesc}
                    onChange={(e) => setSigDesc(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1 font-mono"
                  />
                </div>

                <div className="flex gap-2 pt-2">
                  <button
                    onClick={handleReasonSignal}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium text-xs flex-1"
                  >
                    Reason 5-Question Causality
                  </button>
                  <button
                    onClick={handleDiscoverSignal}
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-medium text-xs flex-1"
                  >
                    Ingest as Lead & Attach to Brain
                  </button>
                </div>
              </div>
            </div>

            {/* 5-Question Causality Output */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">5-Question Causality Breakdown</h2>
              {signalReasoningResult ? (
                <div className="space-y-3 text-xs">
                  <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
                    <span className="font-semibold text-blue-400">1. What Changed?</span>
                    <p className="text-slate-300 mt-1">{signalReasoningResult.five_question_reasoning.q1_what_changed}</p>
                  </div>
                  <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
                    <span className="font-semibold text-purple-400">2. Which Facility / Company is Affected?</span>
                    <p className="text-slate-300 mt-1">{signalReasoningResult.five_question_reasoning.q2_affected_entity}</p>
                  </div>
                  <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
                    <span className="font-semibold text-amber-400">3. How Does it Affect Calibration Requirements?</span>
                    <p className="text-slate-300 mt-1">{signalReasoningResult.five_question_reasoning.q3_calibration_impact}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {signalReasoningResult.likely_parameters.map((p, idx) => (
                        <span key={idx} className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/30">
                          {p}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
                    <span className="font-semibold text-emerald-400">4. How Does it Change Buying Behavior & Price Sensitivity?</span>
                    <p className="text-slate-300 mt-1">{signalReasoningResult.five_question_reasoning.q4_buying_behavior_change}</p>
                  </div>
                  <div className="p-3 bg-slate-800/80 rounded border border-slate-700">
                    <span className="font-semibold text-teal-400">5. What Should Oorja Do Differently?</span>
                    <p className="text-white font-medium mt-1">{signalReasoningResult.five_question_reasoning.q5_oorja_action_strategy}</p>
                    <p className="text-slate-400 mt-1">Recommended Role: <strong className="text-emerald-300">{signalReasoningResult.recommended_target_role}</strong></p>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded">
                  Select a trigger signal and click 'Reason 5-Question Causality' to view the automated commercial chain.
                </div>
              )}

              {signalIngestResult && (
                <div className="p-3 bg-emerald-950/60 border border-emerald-500/40 rounded text-xs text-emerald-300">
                  ✓ Successfully ingested <strong>{signalIngestResult.company_name}</strong> into CRM (ICP Score: {signalIngestResult.icp_score}, Buying Window: {signalIngestResult.buying_window}). Fact & timeline event logged to Company Brain.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 10: CADENCE & HTML EMAIL STUDIO */}
      {!loading && activeTab === "cadence" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* 15-Day Non-Response Evaluator */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">15-Day Non-Response Gate</h2>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-slate-400">Days Since Outbound Dispatch:</label>
                  <input
                    type="number"
                    value={cadenceDays}
                    onChange={(e) => setCadenceDays(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  />
                </div>
                <div>
                  <label className="text-slate-400">Last Contacted Role:</label>
                  <select
                    value={cadenceRole}
                    onChange={(e) => setCadenceRole(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  >
                    <option value="Purchase">Purchase Manager / Procurement</option>
                    <option value="Quality">Quality / Metrology Head</option>
                    <option value="Maintenance">Maintenance Engineer</option>
                  </select>
                </div>
                <button
                  onClick={handleEvaluateCadence}
                  className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium text-xs"
                >
                  Evaluate Cadence Action
                </button>

                {cadenceResult && (
                  <div className="p-3 bg-slate-800 rounded border border-slate-700 mt-3 space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white uppercase text-[11px]">
                        Action: <span className="text-emerald-400">{cadenceResult.action_type?.replace(/_/g, " ")}</span>
                      </span>
                      <span className="text-[10px] text-slate-400">Target: {cadenceResult.target_role}</span>
                    </div>
                    <p className="text-slate-300 text-[11px]">{cadenceResult.reasoning}</p>
                    <div className="pt-2 border-t border-slate-700 text-emerald-300 font-medium">
                      Next Step: {cadenceResult.next_step}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Apollo Live Pilot Validator */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Apollo Pilot Safety Guard</h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  Hard Limit: ≤ 6 Contacts
                </span>
              </div>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-slate-400">Company Name:</label>
                  <input
                    type="text"
                    value={apolloOrgName}
                    onChange={(e) => setApolloOrgName(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  />
                </div>
                <button
                  onClick={handleRunApolloPilot}
                  disabled={apolloLoading}
                  className="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white rounded font-medium text-xs disabled:opacity-50"
                >
                  {apolloLoading ? "Validating..." : "Execute 5-Contact Safe Pilot"}
                </button>

                {apolloPilotResult && (
                  <div className="p-3 bg-slate-800 rounded border border-slate-700 mt-3 space-y-2">
                    <div className="grid grid-cols-2 gap-2 text-[11px]">
                      <div>Requested: <strong>{apolloPilotResult.requested_contacts}</strong></div>
                      <div>Returned: <strong className="text-emerald-400">{apolloPilotResult.returned_contacts}</strong></div>
                      <div>Valid Emails: <strong>{apolloPilotResult.valid_emails_count}</strong></div>
                      <div>Match Accuracy: <strong>{apolloPilotResult.role_match_accuracy_percent}%</strong></div>
                    </div>
                    <p className="text-[10px] text-slate-400 pt-1 border-t border-slate-700">
                      {apolloPilotResult.governance_note}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Dynamic HTML Email Generator */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow space-y-4">
              <h2 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Metrology HTML Email Studio</h2>
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-slate-400">Target Role Template:</label>
                  <select
                    value={emailHtmlRole}
                    onChange={(e) => setEmailHtmlRole(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-white mt-1"
                  >
                    <option value="Quality">Quality (ISO 17025 / Traceability)</option>
                    <option value="Purchase">Purchase (Vendor Consolidation / SLA)</option>
                    <option value="Maintenance">Maintenance (On-Site Downtime Reduction)</option>
                    <option value="Management">Management (Governance & Uncertainty Risk)</option>
                  </select>
                </div>
                <button
                  onClick={handleComposeHtmlEmail}
                  className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded font-medium text-xs"
                >
                  Render Role-Specific HTML Template
                </button>

                {emailHtmlOutput && (
                  <div className="p-3 bg-slate-800 rounded border border-slate-700 mt-3 space-y-2">
                    <div className="font-semibold text-white text-[11px]">
                      Subject: <span className="text-sky-300">{emailHtmlOutput.subject}</span>
                    </div>
                    <div className="p-2 bg-white text-slate-900 rounded text-[10px] font-sans overflow-y-auto max-h-48 border border-slate-300"
                      dangerouslySetInnerHTML={{ __html: emailHtmlOutput.html_content }}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 11: REASONING TRACE & BELIEF STATE */}
      {!loading && activeTab === "reasoning" && beliefStateData && (
        <div className="space-y-6">
          {/* Belief State Summary Banner */}
          <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 shadow flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-xl">🧬</span>
                <h2 className="text-base font-bold text-white tracking-tight">
                  Evidential Belief State: {beliefStateData.company_name}
                </h2>
                <span className="px-2.5 py-0.5 rounded text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  Overall Confidence: {Math.round((beliefStateData.overall_confidence || 0.6) * 100)}%
                </span>
              </div>
              <p className="text-slate-400 text-xs mt-1">
                Evolving probabilistic beliefs with explicit FACT / INFERENCE / HYPOTHESIS epistemic separation and inspectable causal chains.
              </p>
            </div>
            <div className="text-xs text-slate-400">
              Last Reasoned: <span className="text-slate-200">{new Date(beliefStateData.last_reasoned_at).toLocaleTimeString()}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Left Column: Persistent Probabilistic Belief Cards */}
            <div className="space-y-4">
              <h3 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Probabilistic Beliefs</h3>
              
              {/* Calibration Need Belief */}
              {beliefStateData.beliefs?.calibration_need && (
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-white">Calibration Need</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      {beliefStateData.beliefs.calibration_need.epistemic_type}
                    </span>
                  </div>
                  <div className="text-2xl font-bold text-emerald-400">
                    {Math.round(beliefStateData.beliefs.calibration_need.value * 100)}%
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Confidence: <strong className="text-slate-200">{Math.round(beliefStateData.beliefs.calibration_need.confidence * 100)}%</strong>
                  </div>
                  <div className="pt-2 border-t border-slate-800 text-[10px] text-slate-400">
                    <span className="font-semibold text-slate-300">Supporting Evidence:</span>
                    <ul className="list-disc ml-3 mt-1 space-y-0.5 text-slate-300">
                      {(beliefStateData.beliefs.calibration_need.supporting_evidence || []).map((e, idx) => (
                        <li key={idx}>{e}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Buy Probability & Opportunity Value */}
              {beliefStateData.beliefs?.buy_probability && (
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-white">Buy Probability & Value</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      {beliefStateData.beliefs.buy_probability.epistemic_type}
                    </span>
                  </div>
                  <div className="flex justify-between items-baseline">
                    <span className="text-2xl font-bold text-purple-400">
                      {Math.round(beliefStateData.beliefs.buy_probability.value * 100)}%
                    </span>
                    <span className="text-xs font-semibold text-slate-300">
                      Est. ₹{Number(beliefStateData.beliefs.opportunity_value_inr?.value || 150000).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400">
                    Buying Window: <strong className="text-slate-200">{beliefStateData.beliefs.buying_window?.value || "30_days"}</strong> ({beliefStateData.beliefs.buying_window?.epistemic_type})
                  </div>
                </div>
              )}

              {/* Commercial Sensitivities */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                <span className="text-xs font-bold text-white">Commercial Sensitivity Profile</span>
                <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                  <div className="p-2 bg-slate-800 rounded border border-slate-700">
                    <span className="text-[10px] text-slate-400 block">Price Sensitivity</span>
                    <strong className="text-amber-300">{beliefStateData.beliefs?.price_sensitivity?.value || "Medium"}</strong>
                  </div>
                  <div className="p-2 bg-slate-800 rounded border border-slate-700">
                    <span className="text-[10px] text-slate-400 block">Premium Potential</span>
                    <strong className="text-emerald-300">{beliefStateData.beliefs?.premium_potential?.value || "High"}</strong>
                  </div>
                </div>
              </div>

              {/* Add New Evidence Form */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-3">
                <h4 className="text-xs uppercase text-slate-300 tracking-wider font-semibold">Inject Evidential Node</h4>
                <form onSubmit={handleUpdateBeliefWithEvidence} className="space-y-2 text-xs">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] text-slate-400">Epistemic Type:</label>
                      <select
                        value={newEvidenceEpistemic}
                        onChange={(e) => setNewEvidenceEpistemic(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mt-0.5"
                      >
                        <option value="FACT">FACT (Verified)</option>
                        <option value="INFERENCE">INFERENCE (Deduction)</option>
                        <option value="HYPOTHESIS">HYPOTHESIS (Unverified)</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-400">Signal Trigger:</label>
                      <select
                        value={newEvidenceSignal}
                        onChange={(e) => setNewEvidenceSignal(e.target.value)}
                        className="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mt-0.5"
                      >
                        <option value="plant_expansion">Plant Expansion</option>
                        <option value="capex_machining">Machining CAPEX</option>
                        <option value="regulatory_qco">BIS QCO Mandate</option>
                        <option value="qa_headcount">QA Headcount Growth</option>
                        <option value="ev_battery">EV Battery Line</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-400">Evidence Title:</label>
                    <input
                      type="text"
                      value={newEvidenceTitle}
                      onChange={(e) => setNewEvidenceTitle(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mt-0.5"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-400">Source / Provenance:</label>
                    <input
                      type="text"
                      value={newEvidenceSource}
                      onChange={(e) => setNewEvidenceSource(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-white mt-0.5"
                    />
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-400">Contradicting Note (Optional):</label>
                    <input
                      type="text"
                      placeholder="e.g. Procurement noted delay in machine arrival"
                      value={newEvidenceContra}
                      onChange={(e) => setNewEvidenceContra(e.target.value)}
                      className="w-full bg-slate-800 border border-slate-700 rounded p-1.5 text-amber-200 mt-0.5"
                    />
                  </div>

                  <button
                    type="submit"
                    className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded font-medium text-xs mt-1"
                  >
                    Execute Evidential Belief Update
                  </button>
                </form>
              </div>
            </div>

            {/* Middle Column: Contradictions, Research Tasks & Decision Policy Engine */}
            <div className="space-y-4">
              <h3 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Decision Engine & Contradiction Resolver</h3>

              {/* Decision Policy Card */}
              {decisionPolicyData && (
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold text-white">Recommended Tactical Action</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      {decisionPolicyData.decision}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-800 rounded border border-slate-700 space-y-1 text-xs">
                    <p className="font-semibold text-white">Channel: <span className="text-emerald-400">{decisionPolicyData.channel}</span></p>
                    <p className="text-slate-300">Target Role: <strong className="text-sky-300">{decisionPolicyData.target_role}</strong></p>
                    <p className="text-[11px] text-slate-400 pt-1 border-t border-slate-700">{decisionPolicyData.reasoning}</p>
                    <div className="text-[10px] text-slate-500 pt-1">
                      Policy Rule Fired: <code>{decisionPolicyData.policy_rule_fired}</code>
                    </div>
                  </div>
                </div>
              )}

              {/* Active Contradictions */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold text-white">Active Contradictions</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    (beliefStateData.contradictions || []).length > 0
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                  }`}>
                    {(beliefStateData.contradictions || []).length} Detected
                  </span>
                </div>

                {(beliefStateData.contradictions || []).length > 0 ? (
                  <div className="space-y-2">
                    {beliefStateData.contradictions.map((c, idx) => (
                      <div key={idx} className="p-2.5 bg-rose-950/30 border border-rose-500/30 rounded text-xs space-y-1">
                        <p className="text-slate-300"><strong>Source A:</strong> {c.evidence_a}</p>
                        <p className="text-rose-300"><strong>Conflict:</strong> {c.evidence_b}</p>
                        <p className="text-[10px] text-slate-400 italic">{c.resolution_guidance}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No contradictory evidence reported. Evidential alignment is consistent.</p>
                )}
              </div>

              {/* Adaptive Research Tasks */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold text-white">Adaptive Uncertainty-Reduction Tasks</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {(beliefStateData.active_research_tasks || []).length} Pending
                  </span>
                </div>

                {(beliefStateData.active_research_tasks || []).length > 0 ? (
                  <div className="space-y-2">
                    {beliefStateData.active_research_tasks.map((t, idx) => (
                      <div key={idx} className="p-2.5 bg-slate-800 rounded border border-slate-700 text-xs space-y-1">
                        <p className="font-semibold text-amber-300">{t.objective}</p>
                        <p className="text-slate-300 text-[11px]">{t.question_to_answer}</p>
                        <p className="text-[10px] text-slate-400">Recommended Sources: {(t.recommended_sources || []).join(", ")}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">Zero uncertainty debt. No blocking research tasks.</p>
                )}
              </div>
            </div>

            {/* Right Column: Inspectable Causal Traces & Case-Based Reasoning (CBR) */}
            <div className="space-y-4">
              <h3 className="text-xs uppercase text-slate-400 tracking-wider font-semibold">Causal Trace & Case-Based Reasoning</h3>

              {/* Inspectable Causal Chain */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                <span className="text-xs font-bold text-white">Inspectable Causal Traces</span>
                {(beliefStateData.causal_traces || []).length > 0 ? (
                  <div className="space-y-2 overflow-y-auto max-h-64">
                    {beliefStateData.causal_traces.slice(-3).reverse().map((tr, idx) => (
                      <div key={idx} className="p-2.5 bg-slate-800 rounded border border-slate-700 text-xs space-y-1">
                        <div className="flex justify-between items-center text-[10px]">
                          <span className="font-bold text-sky-400">{tr.epistemic_type}: {tr.evidence_title}</span>
                          <span className="text-slate-400">{new Date(tr.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <div className="p-1.5 bg-slate-950 rounded text-[10px] text-emerald-300 font-mono">
                          {tr.causal_path}
                        </div>
                        <div className="text-[10px] text-slate-400 flex justify-between">
                          <span>Need Shift: <strong>{Math.round(tr.resulting_belief_shifts?.calibration_need * 100)}%</strong></span>
                          <span>Confidence: <strong>{Math.round(tr.resulting_belief_shifts?.overall_confidence * 100)}%</strong></span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No causal traces generated yet.</p>
                )}
              </div>

              {/* Case-Based Reasoning (CBR) Benchmark */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 shadow space-y-2">
                <span className="text-xs font-bold text-white">Case-Based Reasoning (CBR) Matches</span>
                <p className="text-[11px] text-slate-400">
                  Matches account characteristics against historical conversion archetypes:
                </p>

                {(cbrCasesData?.similar_archetypes || []).slice(0, 2).map((c, idx) => (
                  <div key={idx} className="p-3 bg-slate-800 rounded border border-slate-700 text-xs space-y-1.5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white">{c.archetype_name}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
                        {Math.round(c.similarity_score * 100)}% Match
                      </span>
                    </div>
                    <p className="text-slate-300 text-[11px]">Typical Deal: <strong>₹{Number(c.expected_deal_size_inr).toLocaleString()}</strong> • Hist. Win Rate: <strong>{Math.round(c.historical_conversion_rate * 100)}%</strong></p>
                    <p className="text-[10px] text-slate-400">Winning Persona: <strong className="text-emerald-300">{c.winning_pitch_role}</strong></p>
                    <p className="text-[10px] text-slate-400 italic">Key Buying Factor: {c.key_buying_factor}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Manual Prospect Onboarding Modal */}
      <CustomerOnboardingModal
        isOpen={showOnboardingModal}
        onClose={() => setShowOnboardingModal(false)}
        onCustomerCreated={(res) => {
          loadCompanies();
          if (res?.company?.id) {
            setSelectedCompanyId(res.company.id);
          }
        }}
      />
    </div>
  );
}
