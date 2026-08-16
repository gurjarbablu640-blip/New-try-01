"""Territory & Industrial Cluster Intelligence for Oorja Sales OS.

Groups plants and prospects into geographical industrial corridors in Gujarat/India
and produces high-ROI on-site visit and audit itineraries.
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models.company import Company
from models.facility import Facility
from models.customer_asset import CustomerAsset
from models.sales_os import Opportunity, Quotation
from services.calibration_intelligence import calculate_asset_due_status


KNOWN_CLUSTERS = {
    "Dahej PCPIR & Port Belt": {
        "cities": ["dahej", "bharuch", "vagra"],
        "estates": ["dahej gidc", "pcpir", "vilayat"],
        "region": "South Gujarat",
        "key_sectors": ["Petrochemicals", "Chlor-Alkali", "Specialty Chemicals", "Ports & Logistics"],
    },
    "Hazira Industrial Zone": {
        "cities": ["hazira", "surat", "ichhapore"],
        "estates": ["hazira gidc", "ichhapore", "sachin"],
        "region": "South Gujarat",
        "key_sectors": ["Heavy Engineering", "Steel & Metals", "Energy", "Cryogenics"],
    },
    "Ankleshwar / Jhagadia Chemical Belt": {
        "cities": ["ankleshwar", "jhagadia", "panoli"],
        "estates": ["ankleshwar gidc", "jhagadia gidc", "panoli gidc"],
        "region": "Central-South Gujarat",
        "key_sectors": ["Pharmaceuticals & API", "Agrochemicals", "Dyes & Pigments"],
    },
    "Vadodara Industrial Corridor": {
        "cities": ["vadodara", "baroda", "nandesari", "savli", "makarpura"],
        "estates": ["nandesari gidc", "makarpura gidc", "savli gidc", "manjusar"],
        "region": "Central Gujarat",
        "key_sectors": ["Switchgear & Power", "Heavy Machinery", "Biotech & Pharma"],
    },
    "Vapi / Sarigam Industrial Hub": {
        "cities": ["vapi", "sarigam", "valsad", "umargam"],
        "estates": ["vapi gidc", "sarigam gidc"],
        "region": "South Gujarat Border",
        "key_sectors": ["Paper & Packaging", "Specialty Chemicals", "Textile Processing"],
    },
    "Sanand & Changodar Engineering Belt": {
        "cities": ["sanand", "changodar", "ahmedabad", "bavla"],
        "estates": ["sanand gidc", "changodar gidc", "kathwada gidc"],
        "region": "North-Central Gujarat",
        "key_sectors": ["Automotive & Auto-ancillary", "Precision Engineering", "EV Components"],
    },
}


def _match_cluster(city: Optional[str], estate: Optional[str] = None) -> str:
    c_lower = (city or "").strip().lower()
    e_lower = (estate or "").strip().lower()

    for cluster_name, meta in KNOWN_CLUSTERS.items():
        if any(c in c_lower for c in meta["cities"]):
            return cluster_name
        if any(e in e_lower for e in meta["estates"]):
            return cluster_name

    return "Other / Emerging Industrial Region"


def get_industrial_clusters(db: Session) -> Dict[str, Any]:
    """Analyze all companies, facilities, and assets grouped by geographical industrial corridor."""
    companies = db.query(Company).all()
    facilities = db.query(Facility).all()
    assets = db.query(CustomerAsset).filter(CustomerAsset.status == "Active").all()
    opportunities = db.query(Opportunity).filter(Opportunity.stage.notin_(["Lost"])).all()

    today = date.today()

    # Build asset lookup by company & facility
    comp_assets: Dict[int, List[CustomerAsset]] = {}
    for a in assets:
        comp_assets.setdefault(a.company_id, []).append(a)

    # Build facility lookup by company
    comp_facs: Dict[int, List[Facility]] = {}
    for f in facilities:
        comp_facs.setdefault(f.company_id, []).append(f)

    # Build opportunity value lookup by company
    comp_opp_val: Dict[int, float] = {}
    for o in opportunities:
        comp_opp_val[o.company_id] = comp_opp_val.get(o.company_id, 0.0) + float(o.estimated_value or 0)

    # Grouping
    cluster_buckets: Dict[str, Dict[str, Any]] = {}

    for c in companies:
        c_facs = comp_facs.get(c.id, [])
        primary_estate = c_facs[0].industrial_estate if c_facs else None
        cluster_name = _match_cluster(c.city, primary_estate)

        if cluster_name not in cluster_buckets:
            meta = KNOWN_CLUSTERS.get(cluster_name, {
                "region": "Other",
                "key_sectors": ["General Manufacturing"],
            })
            cluster_buckets[cluster_name] = {
                "cluster_name": cluster_name,
                "region": meta.get("region", "Other"),
                "key_sectors": meta.get("key_sectors", []),
                "companies_count": 0,
                "facilities_count": 0,
                "total_assets": 0,
                "overdue_assets": 0,
                "due_30d_assets": 0,
                "pipeline_value": 0.0,
                "priority_score": 0.0,
                "companies": [],
            }

        bucket = cluster_buckets[cluster_name]
        bucket["companies_count"] += 1
        bucket["facilities_count"] += len(c_facs)
        bucket["pipeline_value"] += comp_opp_val.get(c.id, 0.0)

        c_asset_list = comp_assets.get(c.id, [])
        bucket["total_assets"] += len(c_asset_list)

        overdue_c = 0
        due_30_c = 0
        for a in c_asset_list:
            if a.calibration_due_date:
                status_info = calculate_asset_due_status(a.calibration_due_date, reference_date=today)
                if status_info["due_status"] == "OVERDUE":
                    overdue_c += 1
                elif status_info["due_status"] == "DUE_NEXT_30_DAYS":
                    due_30_c += 1

        bucket["overdue_assets"] += overdue_c
        bucket["due_30d_assets"] += due_30_c

        # Calculate company score contribution
        c_score = float(c.icp_score or 0)
        bucket["priority_score"] += c_score + (overdue_c * 15.0) + (due_30_c * 8.0)

        bucket["companies"].append({
            "id": c.id,
            "name": c.name,
            "city": c.city,
            "industry": c.industry,
            "lead_status": c.lead_status,
            "icp_score": c.icp_score,
            "buying_window": c.buying_window,
            "asset_count": len(c_asset_list),
            "urgent_assets": overdue_c + due_30_c,
        })

    # Sort clusters by priority score
    results = sorted(cluster_buckets.values(), key=lambda x: x["priority_score"], reverse=True)

    return {
        "total_clusters": len(results),
        "clusters": results,
    }


def get_visit_recommendations(db: Session, max_stops: int = 4) -> Dict[str, Any]:
    """Generate high-density on-site sales/audit route recommendations per cluster."""
    cluster_data = get_industrial_clusters(db)
    recommendations = []

    for cluster in cluster_data["clusters"]:
        # Find companies in this cluster that have urgent calibration needs or active buying windows
        targets = [
            c for c in cluster["companies"]
            if c["urgent_assets"] > 0 or c["buying_window"] in ["next_30_days", "next_60_days"] or (c["icp_score"] or 0) >= 60
        ]

        if not targets:
            continue

        # Sort targets by urgency & ICP
        sorted_targets = sorted(targets, key=lambda x: (x["urgent_assets"] * 10 + (x["icp_score"] or 0)), reverse=True)[:max_stops]

        total_urgent_stops = sum(t["urgent_assets"] for t in sorted_targets)
        est_opportunity = total_urgent_stops * 1500.0  # Estimated calibration spend per instrument

        itinerary_stops = []
        for idx, t in enumerate(sorted_targets, start=1):
            time_slot = f"{9 + (idx - 1) * 2}:30 AM - {11 + (idx - 1) * 2}:30 AM" if idx <= 3 else "03:30 PM - 05:00 PM"
            itinerary_stops.append({
                "stop_number": idx,
                "time_slot": time_slot,
                "company_id": t["id"],
                "company_name": t["name"],
                "city": t["city"],
                "objective": f"On-site audit for {t['urgent_assets']} due instruments & master list review" if t["urgent_assets"] > 0 else "NABL capability introduction & plant walk-through",
                "urgent_instruments": t["urgent_assets"],
            })

        recommendations.append({
            "cluster_name": cluster["cluster_name"],
            "region": cluster["region"],
            "recommended_day": "Recommended Next Tuesday / Thursday",
            "est_calibration_opportunity": est_opportunity,
            "total_stops": len(itinerary_stops),
            "itinerary": itinerary_stops,
        })

    return {
        "generated_date": date.today().isoformat(),
        "total_recommended_routes": len(recommendations),
        "routes": recommendations,
    }
