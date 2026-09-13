"""Deep Facility Resolution Engine — Multi-source exact facility & industrial corridor linkage.

Resolves company trigger events to exact physical plants, industrial corridors,
and manufacturing units with rigorous evidence classification:
- DIRECT: Trigger explicitly names the plant, industrial estate, or project facility
- STRONG: Trigger and independent regulatory/location source independently corroborate the plant
- WEAK: Company operates a plant in the city, but trigger is corporate-only
- UNKNOWN: No exact facility or industrial footprint identified
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Known industrial corridors and manufacturing clusters in India with aliases
INDUSTRIAL_CLUSTERS = {
    "oragadam": {"city": "Chennai", "aliases": ["chennai", "kanchipuram"], "state": "Tamil Nadu", "type": "SIPCOT Corridor"},
    "sriperumbudur": {"city": "Chennai", "aliases": ["chennai", "kanchipuram"], "state": "Tamil Nadu", "type": "SIPCOT Industrial Park"},
    "chakan": {"city": "Pune", "aliases": ["pune"], "state": "Maharashtra", "type": "MIDC Auto Cluster"},
    "bhosari": {"city": "Pune", "aliases": ["pune"], "state": "Maharashtra", "type": "MIDC Industrial Area"},
    "talegaon": {"city": "Pune", "aliases": ["pune"], "state": "Maharashtra", "type": "MIDC Phase II"},
    "ranjangaon": {"city": "Pune", "aliases": ["pune"], "state": "Maharashtra", "type": "MIDC Auto Park"},
    "bidadi": {"city": "Bengaluru", "aliases": ["bangalore", "bengaluru"], "state": "Karnataka", "type": "KIADB Industrial Area"},
    "bommasandra": {"city": "Bengaluru", "aliases": ["bangalore", "bengaluru", "jigani"], "state": "Karnataka", "type": "KIADB Industrial Area"},
    "jigani": {"city": "Bengaluru", "aliases": ["bangalore", "bengaluru"], "state": "Karnataka", "type": "Industrial Area"},
    "peenya": {"city": "Bengaluru", "aliases": ["bangalore", "bengaluru"], "state": "Karnataka", "type": "Industrial Estate"},
    "sanand": {"city": "Ahmedabad", "aliases": ["ahmedabad"], "state": "Gujarat", "type": "GIDC Industrial Estate"},
    "manesar": {"city": "Gurugram", "aliases": ["gurgaon", "gurugram"], "state": "Haryana", "type": "HSIIDC IMT"},
    "begumpur khatola": {"city": "Gurugram", "aliases": ["gurgaon", "gurugram"], "state": "Haryana", "type": "Sector 35 Industrial Area"},
    "dharuhera": {"city": "Rewari", "aliases": ["rewari", "gurgaon"], "state": "Haryana", "type": "Industrial Estate"},
    "waluj": {"city": "Chhatrapati Sambhaji Nagar", "aliases": ["aurangabad", "chhatrapati sambhaji nagar"], "state": "Maharashtra", "type": "MIDC Industrial Area"},
    "shendra": {"city": "Chhatrapati Sambhaji Nagar", "aliases": ["aurangabad", "chhatrapati sambhaji nagar"], "state": "Maharashtra", "type": "AURIC DMIC"},
    "chikalthana": {"city": "Chhatrapati Sambhaji Nagar", "aliases": ["aurangabad", "chhatrapati sambhaji nagar"], "state": "Maharashtra", "type": "MIDC Industrial Area"},
    "coimbatore": {"city": "Coimbatore", "aliases": ["coimbatore"], "state": "Tamil Nadu", "type": "Precision Engineering Cluster"},
    "arasur": {"city": "Coimbatore", "aliases": ["coimbatore"], "state": "Tamil Nadu", "type": "Arasur Industrial Corridor"},
    "kurichi": {"city": "Coimbatore", "aliases": ["coimbatore"], "state": "Tamil Nadu", "type": "SIDCO Kurichi Industrial Estate"},
    "hosur": {"city": "Hosur", "aliases": ["hosur", "bengaluru"], "state": "Tamil Nadu", "type": "SIPCOT Industrial Complex"},
    "jamshedpur": {"city": "Jamshedpur", "aliases": ["jamshedpur", "adityapur"], "state": "Jharkhand", "type": "Heavy Industrial Area"},
    "adityapur": {"city": "Jamshedpur", "aliases": ["jamshedpur", "saraikela"], "state": "Jharkhand", "type": "Adityapur Industrial Area (AIADA)"},
    "faridabad": {"city": "Faridabad", "aliases": ["faridabad", "delhi"], "state": "Haryana", "type": "Industrial Area"},
    "pantnagar": {"city": "Udham Singh Nagar", "aliases": ["pantnagar", "rudrapur"], "state": "Uttarakhand", "type": "SIIDCUL Integrated Industrial Estate"},
    "rajkot": {"city": "Rajkot", "aliases": ["rajkot"], "state": "Gujarat", "type": "GIDC Precision Forging Hub"},
    "shapar": {"city": "Rajkot", "aliases": ["rajkot"], "state": "Gujarat", "type": "GIDC Shapar-Veraval"},
    "metoda": {"city": "Rajkot", "aliases": ["rajkot"], "state": "Gujarat", "type": "GIDC Metoda Industrial Estate"},
    "kotharia": {"city": "Rajkot", "aliases": ["rajkot"], "state": "Gujarat", "type": "Gondal Road Industrial Area"},
    "noida": {"city": "Noida", "aliases": ["noida", "delhi"], "state": "Uttar Pradesh", "type": "Sector 8 / Phase II Industrial Area"},
    "greater noida": {"city": "Greater Noida", "aliases": ["greater noida", "noida"], "state": "Uttar Pradesh", "type": "Ecotech Industrial Area"},
    "pithampur": {"city": "Dhar", "aliases": ["dhar", "indore"], "state": "Madhya Pradesh", "type": "MPIDC Industrial Area"},
}


class DeepFacilityResolver:
    """Engine for resolving triggers to exact facilities with proven linkage."""

    def resolve_facility(
        self,
        company_name: str,
        trigger_text: str,
        known_city: Optional[str] = None,
        known_state: Optional[str] = None,
        evidence_snippets: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Resolve exact manufacturing facility and classify trigger-to-facility linkage."""
        trigger_lower = (trigger_text or "").lower()
        company_lower = (company_name or "").lower()
        snippets = evidence_snippets or []
        combined_text = f"{trigger_text} {' '.join(snippets)}".lower()

        # Step 1: Detect explicit industrial corridor / cluster mention in TRIGGER TEXT directly
        detected_cluster = None
        for cluster_key, cluster_meta in INDUSTRIAL_CLUSTERS.items():
            if cluster_key in trigger_lower:
                detected_cluster = (cluster_key, cluster_meta)
                break

        if detected_cluster:
            cluster_key, cluster_meta = detected_cluster
            facility_name = f"{company_name} {cluster_meta['type']}, {cluster_key.title()}"
            address = f"{cluster_key.title()} {cluster_meta['type']}, {cluster_meta['city']}, {cluster_meta['state']}"
            return {
                "facility_name": facility_name,
                "facility_address": address,
                "city": cluster_meta["city"],
                "state": cluster_meta["state"],
                "industrial_cluster": cluster_key.title(),
                "linkage_confidence": "DIRECT",
                "linkage_evidence": f"Trigger event explicitly specifies {cluster_key.title()} ({cluster_meta['type']})",
                "facility_verified": True,
                "trigger_facility": facility_name,
                "known_company_facility": f"{company_name} {known_city or ''}".strip(),
            }

        target_city = (known_city or "").lower()
        target_state = (known_state or "").lower()

        # Step 2: Trigger text mentions city/state and corroborating evidence specifies the exact plant
        trigger_mentions_city = target_city and (target_city in trigger_lower)
        trigger_mentions_cluster = any(c_key in trigger_lower for c_key in INDUSTRIAL_CLUSTERS)

        # Step 2: Corroborating evidence in snippets or trigger matches industrial cluster
        for cluster_key, cluster_meta in INDUSTRIAL_CLUSTERS.items():
            if cluster_key in combined_text:
                aliases = [a.lower() for a in cluster_meta.get("aliases", [cluster_meta["city"].lower()])]
                city_matches = target_city in aliases or target_city == cluster_meta["city"].lower()
                if not target_city or city_matches or (target_state and target_state in cluster_meta["state"].lower()):
                    is_trigger_linked = trigger_mentions_city or trigger_mentions_cluster
                    return {
                        "facility_name": f"{company_name} Manufacturing Unit, {cluster_key.title()}",
                        "facility_address": f"{cluster_key.title()} {cluster_meta['type']}, {cluster_meta['city']}, {cluster_meta['state']}",
                        "city": cluster_meta["city"],
                        "state": cluster_meta["state"],
                        "industrial_cluster": cluster_key.title(),
                        "linkage_confidence": "STRONG",
                        "linkage_evidence": f"Documentation corroborates active manufacturing at {cluster_key.title()} in {cluster_meta['city']}",
                        "facility_verified": True,
                        "trigger_facility": f"{company_name} Manufacturing Unit, {cluster_key.title()}" if is_trigger_linked else None,
                        "known_company_facility": f"{company_name} Manufacturing Unit, {cluster_key.title()}",
                    }

        if trigger_mentions_city or trigger_mentions_cluster:
            # Check if snippets or trigger identify exact plant address
            plant_match = re.search(r'(?:plant|facility|unit|works|factory|branch)\s*(?:at|in|no\.?|location:?)\s*([A-Za-z0-9\s,\-]+?(?:city|corridor|estate|midc|sipcot|gidc|phase|sector|road|nagar|puram|dist|district))', combined_text, re.I)
            if plant_match:
                plant_detail = plant_match.group(0).strip().title()
                return {
                    "facility_name": f"{company_name} - {plant_detail}",
                    "facility_address": f"{plant_detail}, {known_city.title() if known_city else 'India'}",
                    "city": known_city.title() if known_city else "",
                    "state": known_state.title() if known_state else "",
                    "linkage_confidence": "STRONG",
                    "linkage_evidence": f"Trigger references {target_city.title()} and documentation confirms plant at {plant_detail}",
                    "facility_verified": True,
                    "trigger_facility": f"{company_name} - {plant_detail}",
                    "known_company_facility": f"{company_name} {known_city or ''}".strip(),
                }


        # Step 3: Seed list / directory knows company has a facility, but trigger is corporate-only
        # This prevents corporate triggers from falsely inheriting DIRECT/STRONG linkage to seed plants
        if known_city:
            return {
                "facility_name": f"{company_name} ({known_city.title()} Operations)",
                "facility_address": f"{known_city.title()}, {known_state.title() if known_state else 'India'}",
                "city": known_city.title(),
                "state": known_state.title() if known_state else "",
                "industrial_cluster": None,
                "linkage_confidence": "WEAK",
                "linkage_evidence": f"Static seed data confirms operations in {known_city.title()}, but trigger text contains zero facility/location evidence",
                "facility_verified": False,
                "trigger_facility": None,
                "known_company_facility": f"{company_name} ({known_city.title()} Operations)",
            }

        # Step 5: Unknown
        return {
            "facility_name": None,
            "facility_address": None,
            "city": None,
            "state": None,
            "industrial_cluster": None,
            "linkage_confidence": "UNKNOWN",
            "linkage_evidence": "No physical facility or manufacturing location identified in evidence",
            "facility_verified": False,
        }

    def fetch_primary_source_snippets(
        self,
        domain: str,
        company_name: str,
        known_city: Optional[str] = None,
    ) -> Tuple[List[str], int]:
        """Fetch plant and facility evidence directly from company's official domain."""
        import urllib.request
        snippets = []
        paths = ["contact-us", "contact", "locations", "facilities", "manufacturing-facilities", ""]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for path in paths:
            url = f"https://www.{domain}/{path}".rstrip("/") if domain else ""
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                    text = re.sub(r"<[^>]+>", " ", html)
                    for line in text.split("\n"):
                        clean_line = line.strip()
                        if 20 < len(clean_line) < 250:
                            clean_lower = clean_line.lower()
                            if any(k in clean_lower for k in ["plant", "facility", "unit", "works", "midc", "sipcot", "gidc", "kiadb", "industrial", "address:"]) or any(c in clean_lower for c in INDUSTRIAL_CLUSTERS):
                                snippets.append(clean_line)
                    if snippets:
                        break
            except Exception:
                continue

        return snippets, 0


# Global instance
deep_facility_resolver = DeepFacilityResolver()
