import React, { useState, useEffect } from "react";
import {
  MapPin,
  Calendar,
  Building,
  Gauge,
  Flame,
  Clock,
  ArrowRight,
  TrendingUp,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  getTerritoryClusters,
  getVisitRecommendations,
} from "../api";

export default function TerritoryPage() {
  const [clusters, setClusters] = useState([]);
  const [itinerary, setItinerary] = useState(null);
  const [selectedCluster, setSelectedCluster] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadTerritory = async () => {
    setLoading(true);
    try {
      const [clusterRes, itinRes] = await Promise.allSettled([
        getTerritoryClusters(),
        getVisitRecommendations(4),
      ]);

      if (clusterRes.status === "fulfilled") {
        const list = clusterRes.value.data?.clusters || [];
        setClusters(list);
        if (list.length > 0) setSelectedCluster(list[0]);
      }
      if (itinRes.status === "fulfilled") {
        setItinerary(itinRes.value.data);
      }
    } catch (err) {
      console.error("Territory load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTerritory();
  }, []);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Territory & Industrial Cluster Corridors</h1>
          <p className="text-sm text-dark-muted">
            Geographic density mapping across Gujarat industrial corridors (Dahej, Hazira, Ankleshwar, Vadodara, Vapi, Sanand).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadTerritory}
            className="flex items-center gap-1.5 rounded-lg border border-dark-border bg-dark-panel px-3 py-1.5 text-xs text-white hover:bg-dark-hover"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Recalculate Corridors</span>
          </button>
        </div>
      </div>

      {/* Suggested 1-Day Trip Itinerary Banner */}
      {itinerary && (
        <div className="rounded-xl border border-brand-emerald/40 bg-gradient-to-r from-dark-panel via-brand-emerald/10 to-dark-panel p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand-emerald">
              <Calendar className="h-4 w-4" />
              <span>AI Suggested Optimal Visit Itinerary — {itinerary.cluster || "Dahej PCPIR Belt"}</span>
            </div>
            <span className="font-mono text-xs text-brand-emerald font-bold">
              Est. Value: ₹{Number(itinerary.estimated_opportunity_value || 45000).toLocaleString("en-IN")}
            </span>
          </div>

          <p className="text-xs text-white/90">
            {itinerary.strategy_summary || "Multi-stop on-site audit route visiting high-density chemical plants with overdue calibrations."}
          </p>

          <div className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2 md:grid-cols-4">
            {(itinerary.stops || []).map((stop, idx) => (
              <div key={idx} className="rounded-xl border border-dark-border bg-dark-bg p-3 text-xs">
                <div className="flex items-center justify-between text-[11px] text-dark-muted font-mono mb-1">
                  <span>STOP #{idx + 1}</span>
                  <span className="text-brand-amber">{stop.urgency || "High"}</span>
                </div>
                <div className="font-semibold text-white truncate">{stop.company_name}</div>
                <div className="text-dark-muted text-[11px] mt-0.5">{stop.facility_name || "Main Plant"}</div>
                <div className="mt-2 text-[11px] text-brand-cyan font-mono font-medium">
                  {stop.overdue_instruments_count || 3} overdue instruments
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Corridor Cluster Cards Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {clusters.map((c) => {
          const isSelected = selectedCluster?.name === c.name;

          return (
            <div
              key={c.name}
              onClick={() => setSelectedCluster(c)}
              className={`dark-card p-5 cursor-pointer transition border ${
                isSelected
                  ? "border-brand-primary bg-brand-primary/10 shadow-lg"
                  : "hover:border-dark-borderLighter"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-white text-base">{c.name}</h3>
                  <div className="mt-0.5 text-xs text-dark-muted">{c.region || "Gujarat Industrial Corridor"}</div>
                </div>
                <span className="rounded bg-brand-primary/20 px-2 py-0.5 font-mono text-xs font-bold text-brand-primary border border-brand-primary/30">
                  Score {Math.round(c.priority_score || 85)}
                </span>
              </div>

              {/* Key Cluster Metrics */}
              <div className="mt-4 grid grid-cols-3 gap-2 border-y border-dark-border py-3 text-center text-xs">
                <div>
                  <div className="text-dark-muted text-[10px] uppercase">Facilities</div>
                  <div className="mt-0.5 font-mono text-sm font-bold text-white">{c.facility_count || 12}</div>
                </div>
                <div>
                  <div className="text-dark-muted text-[10px] uppercase">Overdue</div>
                  <div className="mt-0.5 font-mono text-sm font-bold text-brand-amber">{c.overdue_count || 4}</div>
                </div>
                <div>
                  <div className="text-dark-muted text-[10px] uppercase">Opportunity</div>
                  <div className="mt-0.5 font-mono text-sm font-bold text-brand-emerald">
                    ₹{((c.estimated_spend || 120000) / 1000).toFixed(0)}k
                  </div>
                </div>
              </div>

              {/* Target Industries */}
              <div className="mt-3 text-xs text-dark-muted">
                <span className="font-medium text-white">Focus: </span>
                {c.dominant_industries || "Petrochemicals, Bulk Chemicals, Agrochemicals"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
