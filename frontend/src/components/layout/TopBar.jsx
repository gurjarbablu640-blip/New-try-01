import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  Plus,
  Bot,
  Bell,
  CheckCircle2,
  ShieldCheck,
  Building,
  FileText,
  Send,
  Calendar,
  Sparkles,
  Command,
} from "lucide-react";
import { searchCompanies } from "../../api";

export default function TopBar({ onOpenCompany, collapsed }) {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showQuickAdd, setShowQuickAdd] = useState(false);

  useEffect(() => {
    if (!searchQuery.trim() || searchQuery.length < 2) {
      setSearchResults([]);
      setIsSearching(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      try {
        const res = await searchCompanies(searchQuery, 6);
        setSearchResults(res.data?.results || res.data || []);
      } catch (err) {
        console.error("Search error:", err);
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  return (
    <header
      className={`sticky top-0 z-30 flex h-16 items-center justify-between border-b border-dark-border bg-[#0A0E17]/90 px-6 backdrop-blur-md transition-all duration-300 ${
        collapsed ? "left-20" : "left-64"
      }`}
    >
      {/* Global Search Bar */}
      <div className="relative w-96">
        <div className="relative flex items-center">
          <Search className="absolute left-3.5 h-4 w-4 text-dark-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search companies, plants, quotes, contacts..."
            className="w-full rounded-lg border border-dark-border bg-dark-panel py-2 pl-10 pr-12 text-sm text-white placeholder-dark-muted shadow-inner focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
          <div className="absolute right-3 flex items-center gap-0.5 rounded border border-dark-border bg-dark-bg px-1.5 py-0.5 text-[10px] font-mono text-dark-muted">
            <Command className="h-3 w-3" /> K
          </div>
        </div>

        {/* Search Results Dropdown */}
        {searchResults.length > 0 && (
          <div className="absolute left-0 right-0 top-full mt-2 overflow-hidden rounded-xl border border-dark-border bg-dark-panel p-1.5 shadow-2xl">
            <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-dark-muted">
              Matching Accounts ({searchResults.length})
            </div>
            {searchResults.map((item) => (
              <div
                key={item.id}
                onClick={() => {
                  onOpenCompany(item.id);
                  setSearchQuery("");
                  setSearchResults([]);
                }}
                className="flex cursor-pointer items-center justify-between rounded-lg px-3 py-2 text-sm text-white transition hover:bg-dark-hover"
              >
                <div className="flex items-center gap-2.5">
                  <Building className="h-4 w-4 text-brand-primary" />
                  <div>
                    <div className="font-medium text-white">{item.name}</div>
                    <div className="text-xs text-dark-muted">{item.city || "Gujarat"} • {item.industry || "Manufacturing"}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded bg-dark-bg px-2 py-0.5 text-[11px] font-mono text-brand-cyan">
                    ICP {Math.round(item.icp_score || 0)}
                  </span>
                  <span className="text-xs text-dark-muted capitalize">{item.lead_status || "Lead"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Action Controls & Indicators */}
      <div className="flex items-center gap-3">
        {/* Outbound Test Mode Badge */}
        <div className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span>Outbound Safe Mode</span>
        </div>

        {/* Ask Oorja Quick AI button */}
        <button
          onClick={() => navigate("/assistant")}
          className="flex items-center gap-2 rounded-lg border border-brand-primary/40 bg-gradient-to-r from-brand-primary/20 to-brand-secondary/20 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:border-brand-primary hover:from-brand-primary/30 hover:to-brand-secondary/30"
        >
          <Bot className="h-4 w-4 text-brand-cyan" />
          <span>Ask Oorja AI</span>
        </button>

        {/* Quick Add Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowQuickAdd(!showQuickAdd)}
            className="flex items-center gap-1.5 rounded-lg bg-brand-primary px-3 py-1.5 text-xs font-semibold text-white shadow transition hover:bg-brand-primaryHover"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Quick Action</span>
          </button>

          {showQuickAdd && (
            <div className="absolute right-0 top-full mt-2 w-52 overflow-hidden rounded-xl border border-dark-border bg-dark-panel p-1 shadow-2xl">
              <button
                onClick={() => {
                  setShowQuickAdd(false);
                  navigate("/leads");
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs text-white transition hover:bg-dark-hover"
              >
                <Plus className="h-3.5 w-3.5 text-brand-primary" />
                <span>Search New Lead (Apollo)</span>
              </button>
              <button
                onClick={() => {
                  setShowQuickAdd(false);
                  navigate("/quotations");
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs text-white transition hover:bg-dark-hover"
              >
                <FileText className="h-3.5 w-3.5 text-brand-cyan" />
                <span>Generate Quotation</span>
              </button>
              <button
                onClick={() => {
                  setShowQuickAdd(false);
                  navigate("/campaigns");
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs text-white transition hover:bg-dark-hover"
              >
                <Send className="h-3.5 w-3.5 text-brand-secondary" />
                <span>Create Campaign</span>
              </button>
              <button
                onClick={() => {
                  setShowQuickAdd(false);
                  navigate("/territory");
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs text-white transition hover:bg-dark-hover"
              >
                <Calendar className="h-3.5 w-3.5 text-brand-amber" />
                <span>Plan Cluster Visit</span>
              </button>
            </div>
          )}
        </div>

        {/* User Pill */}
        <div className="flex items-center gap-2 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white">
          <div className="h-2 w-2 rounded-full bg-emerald-500"></div>
          <span className="font-medium">Oorja Metrology Sales</span>
        </div>
      </div>
    </header>
  );
}
