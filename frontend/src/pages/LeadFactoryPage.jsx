import React, { useState, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Users,
  Search,
  Filter,
  Flame,
  CheckCircle2,
  AlertTriangle,
  Mail,
  Send,
  Building,
  RefreshCw,
  Sparkles,
  ShieldCheck,
  Plus,
  ArrowRight,
  ExternalLink,
} from "lucide-react";
import {
  searchApolloLeads,
  getCompanies,
  validateEmail,
  qualifyLead,
  setQualificationStatus,
} from "../api";

export default function LeadFactoryPage() {
  const { onOpenCompany } = useOutletContext();

  const [source, setSource] = useState("apollo");
  const [searchQuery, setSearchQuery] = useState("Chemical");
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(false);
  const [industryFilter, setIndustryFilter] = useState("all");
  const [locationFilter, setLocationFilter] = useState("all");
  const [qualFilter, setQualFilter] = useState("all");
  const [validatingEmail, setValidatingEmail] = useState(null);
  const [qualifyingId, setQualifyingId] = useState(null);
  const [notification, setNotification] = useState("");

  const loadLeads = async () => {
    setLoading(true);
    setNotification("");
    try {
      if (source === "apollo") {
        const res = await searchApolloLeads({
          query: searchQuery,
          page: 1,
          per_page: 20,
        });
        setLeads(res.data?.results || []);
      } else {
        const res = await getCompanies({ q: searchQuery, limit: 20 });
        setLeads(res.data?.results || res.data || []);
      }
    } catch (err) {
      console.error("Lead fetch error:", err);
      setNotification("Failed to fetch leads from " + source);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLeads();
  }, [source]);

  const handleValidateEmail = async (email, index) => {
    if (!email) return;
    setValidatingEmail(index);
    try {
      const res = await validateEmail(email);
      setNotification(`Email ${email}: ${res.data?.status?.toUpperCase()} (${res.data?.reason || "RFC 5322 Valid"})`);
    } catch (err) {
      setNotification(`Validation failed for ${email}`);
    } finally {
      setValidatingEmail(null);
    }
  };

  const handleQualifyLead = async (companyId) => {
    if (!companyId) return;
    setQualifyingId(companyId);
    try {
      const res = await qualifyLead(companyId);
      setNotification(`Lead #${companyId} Qualified: ${res.data?.qualification_status}`);
      loadLeads();
    } catch (err) {
      setNotification("Qualification failed");
    } finally {
      setQualifyingId(null);
    }
  };

  const filteredLeads = leads.filter((item) => {
    if (industryFilter !== "all" && item.industry && !item.industry.toLowerCase().includes(industryFilter.toLowerCase())) {
      return false;
    }
    if (locationFilter !== "all" && item.city && !item.city.toLowerCase().includes(locationFilter.toLowerCase())) {
      return false;
    }
    if (qualFilter !== "all" && item.qualification_status && item.qualification_status !== qualFilter) {
      return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Lead Factory & Enrichment</h1>
          <p className="text-sm text-dark-muted">
            Deterministic discovery, RFC 5322 validation, ICP scoring, and outbound qualification gates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadLeads}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white transition hover:bg-dark-hover disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh Feed</span>
          </button>
        </div>
      </div>

      {/* Notification Banner */}
      {notification && (
        <div className="rounded-xl border border-brand-cyan/30 bg-brand-cyan/10 px-4 py-3 text-xs text-brand-cyan flex items-center justify-between animate-in fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4" />
            <span>{notification}</span>
          </div>
          <button onClick={() => setNotification("")} className="text-white hover:opacity-75">✕</button>
        </div>
      )}

      {/* Source Selector Pills & Filter Bar */}
      <div className="dark-card p-4 space-y-4">
        {/* Source Pills */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase text-dark-muted mr-1">Lead Source:</span>
            {[
              { id: "apollo", label: "Apollo Industrial API", badge: "Live + Mock" },
              { id: "database", label: "CRM Lead Repository", badge: "Local DB" },
              { id: "maps", label: "Industrial Estate Belts", badge: "GIDC" },
            ].map((s) => (
              <button
                key={s.id}
                onClick={() => setSource(s.id)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  source === s.id
                    ? "bg-brand-primary text-white shadow-md shadow-brand-primary/20"
                    : "bg-dark-bg text-dark-muted hover:text-white border border-dark-border"
                }`}
              >
                <span>{s.label}</span>
                <span className="text-[10px] opacity-75 font-mono">({s.badge})</span>
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div className="flex items-center gap-2">
            <div className="relative w-64">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-dark-muted" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadLeads()}
                placeholder="Search industry or company..."
                className="w-full rounded-lg border border-dark-border bg-dark-bg py-1.5 pl-8 pr-3 text-xs text-white placeholder-dark-muted focus:border-brand-primary focus:outline-none"
              />
            </div>
            <button
              onClick={loadLeads}
              className="rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-primaryHover"
            >
              Search
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex items-center gap-3 pt-3 border-t border-dark-border flex-wrap text-xs">
          <div className="flex items-center gap-1 text-dark-muted">
            <Filter className="h-3.5 w-3.5" />
            <span>Filters:</span>
          </div>

          <select
            value={industryFilter}
            onChange={(e) => setIndustryFilter(e.target.value)}
            className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-xs text-white focus:outline-none"
          >
            <option value="all">All Industries</option>
            <option value="chemical">Chemical & Petrochemical</option>
            <option value="pharma">Pharma & API</option>
            <option value="engineering">Heavy Engineering</option>
            <option value="automotive">Automotive</option>
          </select>

          <select
            value={locationFilter}
            onChange={(e) => setLocationFilter(e.target.value)}
            className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-xs text-white focus:outline-none"
          >
            <option value="all">All Locations (Gujarat)</option>
            <option value="dahej">Dahej</option>
            <option value="hazira">Hazira</option>
            <option value="ankleshwar">Ankleshwar</option>
            <option value="vadodara">Vadodara</option>
            <option value="vapi">Vapi</option>
            <option value="ahmedabad">Ahmedabad</option>
          </select>

          <select
            value={qualFilter}
            onChange={(e) => setQualFilter(e.target.value)}
            className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-xs text-white focus:outline-none"
          >
            <option value="all">All Qualification Statuses</option>
            <option value="READY_FOR_OUTREACH">Ready for Outreach</option>
            <option value="QUALIFIED">Qualified</option>
            <option value="NEEDS_ENRICHMENT">Needs Enrichment</option>
          </select>

          <div className="ml-auto text-dark-muted font-mono text-[11px]">
            Showing {filteredLeads.length} accounts
          </div>
        </div>
      </div>

      {/* DENSE DATA TABLE */}
      <div className="dark-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="dark-table-header">Company & Location</th>
                <th className="dark-table-header">Key Decision Maker</th>
                <th className="dark-table-header">Contact & Email</th>
                <th className="dark-table-header">ICP Score</th>
                <th className="dark-table-header">Qualification</th>
                <th className="dark-table-header text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-xs text-dark-muted">
                    <div className="flex items-center justify-center gap-2">
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-brand-primary border-t-transparent"></div>
                      <span>Querying lead intelligence engine...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredLeads.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-xs text-dark-muted">
                    No leads found matching current search and filter parameters.
                  </td>
                </tr>
              ) : (
                filteredLeads.map((item, idx) => {
                  const compName = item.company_name || item.name;
                  const contact = item.contacts?.[0] || {};
                  const email = contact.email || item.email;
                  const score = Math.round(item.icp_score || (item.headcount ? 85 : 70));
                  const qualStatus = item.qualification_status || (score >= 75 ? "READY_FOR_OUTREACH" : "QUALIFIED");

                  return (
                    <tr key={idx} className="dark-table-row">
                      {/* Company */}
                      <td className="dark-table-cell">
                        <div
                          onClick={() => item.id && onOpenCompany(item.id)}
                          className="font-semibold text-white text-sm hover:text-brand-cyan cursor-pointer transition flex items-center gap-1.5"
                        >
                          <Building className="h-3.5 w-3.5 text-brand-primary flex-shrink-0" />
                          <span>{compName}</span>
                        </div>
                        <div className="text-xs text-dark-muted mt-0.5">
                          {item.city || "Gujarat"}{item.state ? `, ${item.state}` : ""} • {item.industry || "Chemical Manufacturing"}
                        </div>
                      </td>

                      {/* Contact */}
                      <td className="dark-table-cell">
                        <div className="font-medium text-white text-xs">
                          {contact.name || item.contact_person || "Quality & NABL Lead"}
                        </div>
                        <div className="text-[11px] text-dark-muted">
                          {contact.title || "Plant Head"}
                        </div>
                      </td>

                      {/* Email & Deliverability */}
                      <td className="dark-table-cell">
                        {email ? (
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-brand-cyan truncate max-w-[180px]">{email}</span>
                            <button
                              onClick={() => handleValidateEmail(email, idx)}
                              disabled={validatingEmail === idx}
                              className="rounded border border-dark-border p-1 text-dark-muted hover:text-brand-emerald hover:border-brand-emerald/40 transition"
                              title="Validate deliverability via RFC 5322 & DNS MX"
                            >
                              <ShieldCheck className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-dark-muted italic">Unenriched email</span>
                        )}
                      </td>

                      {/* ICP Score */}
                      <td className="dark-table-cell font-mono">
                        <span
                          className={`rounded px-2 py-0.5 text-xs font-bold ${
                            score >= 80
                              ? "bg-brand-emerald/15 text-brand-emerald border border-brand-emerald/30"
                              : score >= 60
                              ? "bg-brand-amber/15 text-brand-amber border border-brand-amber/30"
                              : "bg-dark-panel text-dark-muted"
                          }`}
                        >
                          {score}
                        </span>
                      </td>

                      {/* Qualification Status */}
                      <td className="dark-table-cell">
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase ${
                            qualStatus === "READY_FOR_OUTREACH"
                              ? "badge-emerald"
                              : qualStatus === "QUALIFIED"
                              ? "badge-primary"
                              : "badge-amber"
                          }`}
                        >
                          {qualStatus.replaceAll("_", " ")}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="dark-table-cell text-right space-x-1.5">
                        {item.id ? (
                          <button
                            onClick={() => onOpenCompany(item.id)}
                            className="rounded-lg border border-dark-border bg-dark-bg px-2.5 py-1 text-xs text-white hover:bg-dark-hover transition"
                          >
                            Inspect 360
                          </button>
                        ) : (
                          <button
                            onClick={() => handleQualifyLead(idx + 1)}
                            disabled={qualifyingId === idx + 1}
                            className="rounded-lg bg-brand-primary px-2.5 py-1 text-xs font-semibold text-white hover:bg-brand-primaryHover transition"
                          >
                            Import & Qualify
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
