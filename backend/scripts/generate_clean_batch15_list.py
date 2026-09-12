"""Curates Batch 15 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
import os
import sys
import re
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load all used companies across all previous batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES
from scripts.prepare_batch4_company_list import BATCH_4_COMPANIES
from scripts.prepare_batch5_company_list import BATCH_5_COMPANIES
from scripts.prepare_batch6_company_list import BATCH_6_COMPANIES
from scripts.prepare_batch7_company_list import BATCH_7_COMPANIES
from scripts.prepare_batch8_company_list import BATCH_8_COMPANIES
from scripts.prepare_batch9_company_list import BATCH_9_COMPANIES
from scripts.prepare_batch10_company_list import BATCH_10_COMPANIES
from scripts.prepare_batch11_company_list import BATCH_11_COMPANIES
from scripts.prepare_batch12_company_list import BATCH_12_COMPANIES
from scripts.prepare_batch13_company_list import BATCH_13_COMPANIES
from scripts.prepare_batch14_company_list import BATCH_14_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

all_used_names = set()
for c in BATCH_100_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_3_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_4_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_5_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_6_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_7_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_8_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_9_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_10_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_11_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_12_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_13_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_14_COMPANIES:
    all_used_names.add(c["name"].lower().strip())

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-14): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Group 1: Heavy Industrial Equipment & Flow
    {"name": "Veljan Denison Limited", "domain": "veljan.com", "sector": "Hydraulic Pumps, Motors, Directional Valves & Manifold Blocks", "primary_hub": "Patancheru Hyderabad Telangana"},
    {"name": "Jayaswal Neco Industries Limited", "domain": "necoindia.com", "sector": "Centrifugal Cast Iron Pipes, Steel Billets & Heavy Foundry Castings", "primary_hub": "Siltara Raipur Chhattisgarh / Nagpur"},
    {"name": "Balmer Lawrie & Company Limited - Industrial Packaging", "domain": "balmerlawrie.com", "sector": "Steel Barrels, Drums & Grease Formulations", "primary_hub": "Taloja / Asaoti / Chennai / Silvassa"},
    {"name": "RTS Power Corporation Limited", "domain": "rtspower.com", "sector": "Distribution & Power Transformers, Dry Type Transformers", "primary_hub": "Jaipur Rajasthan / Kolkata"},
    {"name": "WS Industries (India) Limited", "domain": "wsindustries.in", "sector": "Porcelain Transmission Insulators & Substation Surge Arresters", "primary_hub": "Porur Chennai Tamil Nadu"},
    {"name": "Goa Carbon Limited", "domain": "goacarbon.com", "sector": "Calcined Petroleum Coke for Aluminium Smelters", "primary_hub": "St. Jose de Areal Goa / Paradeep / Bilaspur"},
    {"name": "Premier Polyfilm Limited", "domain": "premierpoly.com", "sector": "Calendered PVC Flooring, Artificial Leather & Geomembranes", "primary_hub": "Bulandshahr UP / Sikandrabad"},
    {"name": "Panyam Cements & Mineral Industries Limited", "domain": "panyamcements.com", "sector": "Portland Cement, Clinker & Lime Products", "primary_hub": "Cement Nagar Kurnool Andhra Pradesh"},
    {"name": "Deccan Cements Limited", "domain": "deccancements.com", "sector": "Special Grade Portland Slag Cement & Clinker Kilns", "primary_hub": "Bhavanipuram Nalgonda Telangana"},

    # Group 2: Mining Machinery, Agro Tractors & Specialty Materials
    {"name": "Eimco Elecon (India) Limited", "domain": "eimcoelecon.in", "sector": "Underground Mining Loaders, Coal Mining Machinery & Drill Rigs", "primary_hub": "Vallabh Vidyanagar Anand Gujarat"},
    {"name": "Thejo Engineering Limited", "domain": "thejo-eng.com", "sector": "Conveyor Belt Splicing, Rubber Linings & Bulk Handling Systems", "primary_hub": "Ponneri / Chennai Tamil Nadu"},
    {"name": "VST Tillers Tractors Limited", "domain": "vsttractors.com", "sector": "Power Tillers, Compact 4WD Tractors & Diesel Engines", "primary_hub": "Hosur Tamil Nadu / Malur Karnataka"},
    {"name": "Chemplast Sanmar Limited", "domain": "chemplastsanmar.com", "sector": "Specialty Paste PVC Resin, Chloromethanes & Caustic Soda Plants", "primary_hub": "Mettur Dam Salem / Cuddalore / Karaikal"},
    {"name": "Privi Speciality Chemicals Limited", "domain": "privi.com", "sector": "Aroma Chemicals, Pinene-based Terpene Derivatives & Fragrances", "primary_hub": "Mahad Raigad Maharashtra / Jhagadia"},
    {"name": "Chemcon Speciality Chemicals Limited", "domain": "cscpl.com", "sector": "Hexamethyldisilazane (HMDS), Chloromethyl Isopropyl Carbonate (CMIC)", "primary_hub": "Manjusar Vadodara Gujarat"},
    {"name": "Marine Electricals (India) Limited", "domain": "marineelectricals.com", "sector": "Marine Switchboards, Power Distribution Panels & Control Consoles", "primary_hub": "Kanjurmarg Mumbai / Goa"},

    # Group 3: Industrial Paper, Packaging & Defense
    {"name": "Star Paper Mills Limited", "domain": "starpapers.com", "sector": "Specialty Packaging Papers, Heavy Kraft & Poster Papers", "primary_hub": "Saharanpur Uttar Pradesh"},
    {"name": "Ruchira Papers Limited", "domain": "ruchirapapers.com", "sector": "Kraft Paper for Corrugated Boxes & Writing/Printing Papers", "primary_hub": "Kala Amb Sirmaur Himachal Pradesh"},
    {"name": "Azad Engineering Limited", "domain": "azad.in", "sector": "Complex Rotating Airfoil Blades & Aerospace Turbine Components", "primary_hub": "Jeedimetla Hyderabad Telangana"},
    {"name": "Venus Pipes & Tubes Limited", "domain": "venuspipes.com", "sector": "Stainless Steel High Pressure Seamless & Welded Industrial Pipes", "primary_hub": "Bhuj Kutch Gujarat"},
    {"name": "Hariom Pipe Industries Limited", "domain": "hariompipes.com", "sector": "Sponge Iron, MS Billets & High Tensile Galvanized Pipes", "primary_hub": "Mahabubnagar Telangana / Bellary Karnataka"},
    {"name": "Aeroflex Industries Limited", "domain": "aeroflexindia.com", "sector": "Stainless Steel Corrugated Flexible Hoses, Braided Assemblies & Fittings", "primary_hub": "Taloja Navi Mumbai Maharashtra"},

    # Group 4: Cement, Plywood, Decorative Laminates & Batteries
    {"name": "Prism Johnson Limited - Cement Division", "domain": "prismjohnson.in", "sector": "Champion Brand Portland Pozzolana Cement & Clinker Units", "primary_hub": "Mankahari Satna Madhya Pradesh"},
    {"name": "Saurashtra Cements Limited", "domain": "saurashtracement.com", "sector": "Hathi Brand Ordinary Portland Cement & Clinker Plants", "primary_hub": "Ranavav Porbandar Gujarat"},
    {"name": "Greenply Industries Limited", "domain": "greenply.com", "sector": "Industrial Plywood, Blockboards & Medium Density Fibreboard", "primary_hub": "Tizit Mon Nagaland / Bamanbore Gujarat / Sandila"},
    {"name": "Century Plyboards (India) Limited", "domain": "centuryply.com", "sector": "Commercial Plywood, Decorative Veneers & Particle Boards", "primary_hub": "Joka Kolkata / Karnal Haryana / Gandhidham / Hoshiarpur"},
    {"name": "Stylam Industries Limited", "domain": "stylam.com", "sector": "High Pressure Decorative Laminates & Exterior Cladding Panels", "primary_hub": "Manak Tabra Panchkula Haryana"},
    {"name": "Rushil Decor Limited", "domain": "rushil.com", "sector": "VIR Brand Plain & Pre-Laminated MDF Boards, Decorative Laminates", "primary_hub": "Gadhoda Gujarat / Chikmagalur Karnataka / Atchutapuram"},
    {"name": "Indo National Limited", "domain": "nippobatteries.com", "sector": "Nippo Brand Dry Cell Batteries & Emergency LED Lighting Products", "primary_hub": "Nellore Tada Andhra Pradesh"},
    {"name": "Mirza International Limited", "domain": "mirza.co.in", "sector": "RedTape Leather Footwear, Automated Tannery & Leather Goods", "primary_hub": "Unnao Uttar Pradesh / Greater Noida"},

    # Group 5: Specialty Industrial Chemicals, Carbon & Fertilizers
    {"name": "Excel Industries Limited", "domain": "excelind.co.in", "sector": "Specialty Chemicals, Phosphorus Intermediates & Biopesticides", "primary_hub": "Roha / Lote Parshuram Maharashtra"},
    {"name": "Punjab Chemicals and Crop Protection Limited", "domain": "punjabchemicals.com", "sector": "Fine Chemicals, Agrochemical Actives & Phosphorus Derivatives", "primary_hub": "Derabassi Mohali Punjab"},
    {"name": "PCBL Limited", "domain": "pcblltd.com", "sector": "Carbon Black for Tyres, Performance Plastics & Specialty Inks", "primary_hub": "Paleij Gujarat / Durgapur / Kochi / Chennai"},
    {"name": "Rain Industries Limited", "domain": "rain-industries.com", "sector": "Calcined Petroleum Coke, Coal Tar Distillation & Specialty Resins", "primary_hub": "Visakhapatnam AP / Bellary Karnataka"},
    {"name": "The Andhra Sugars Limited", "domain": "theandhrasugars.com", "sector": "White Crystal Sugar, Caustic Soda, Industrial Alcohol & Rocket Fuel Chemicals", "primary_hub": "Tanuku West Godavari Andhra Pradesh / Kovvur"},

    # Group 6: Electricals, Secondary Metals & Recycling
    {"name": "RR Kabel Limited", "domain": "rrkabel.com", "sector": "Building Wires, Flame Retardant Cables & Consumer Electricals", "primary_hub": "Silvassa / Waghodia Vadodara Gujarat"},
    {"name": "Gravita India Limited", "domain": "gravitaindia.com", "sector": "Secondary Lead Smelting, Lead Refining & Aluminium Alloys", "primary_hub": "Phagi Jaipur Rajasthan / Chittoor AP / Gandhidham"},
    {"name": "Nile Limited", "domain": "nilelimited.com", "sector": "Pure Lead, Lead Antimonial Alloys & Plastic Masterbatches", "primary_hub": "Choutuppal Nalgonda Telangana / Tirupati AP"},
    {"name": "Pondy Oxides and Chemicals Limited", "domain": "pocl.co.in", "sector": "Secondary Lead Smelting, Lead Sub-Oxide & Metallic Alloys", "primary_hub": "Sriperumbudur Kanchipuram Tamil Nadu"},
    {"name": "Gujarat Themis Biosyn Limited", "domain": "gtbl.in", "sector": "Fermentation Biotechnology, Rifamycin S & Lovastatin", "primary_hub": "Vapi Valsad Gujarat"},

    # Group 7: Fertilizers & Specialty Textiles
    {"name": "Gujarat State Fertilizers & Chemicals Limited", "domain": "gsfclimited.com", "sector": "Sardar Brand Urea, Ammonium Sulphate, Caprolactam & Melamine", "primary_hub": "Fertilizernagar Vadodara Gujarat / Sikka Jamnagar"},
    {"name": "Indo Count Industries Limited", "domain": "indocount.com", "sector": "Automated Spinning, Weaving & Home Textile Processing Plants", "primary_hub": "Kolhapur / Gokul Shirgaon Maharashtra / Bhilad"},
    {"name": "Himatsingka Seide Limited", "domain": "himatsingka.com", "sector": "Drapery Fabrics, Bed Linen Processing & Fine Spinning Plants", "primary_hub": "Doddaballapur Bengaluru / Hassan Karnataka"},
    {"name": "Century Enka Limited", "domain": "centuryenka.com", "sector": "Nylon Tyre Cord Fabrics & High Tenacity Nylon Industrial Yarns", "primary_hub": "Bhosari Pune Maharashtra / Mahad"},
    {"name": "Siyaram Silk Mills Limited", "domain": "siyaram.com", "sector": "Poly-Viscose Suiting, Shirting & Yarn Dyeing Complexes", "primary_hub": "Tarapur Thane Maharashtra / Daman"},

    # Group 8: Active Pharmaceutical Ingredients & Bulk Actives
    {"name": "Hikal Limited", "domain": "hikal.com", "sector": "Crop Protection Actives, Pharmaceutical APIs & Custom Synthesis", "primary_hub": "Taloja / Mahad Maharashtra / Panoli Gujarat / Jigani"},
    {"name": "Aarti Drugs Limited", "domain": "aartidrugs.com", "sector": "Active Pharmaceutical Ingredients, Specialty Chemicals & Formulations", "primary_hub": "Tarapur Thane Maharashtra / Sarigam Gujarat"},
    {"name": "Strides Pharma Science Limited", "domain": "strides.com", "sector": "Oral Solid Dosages, Sterile Injectables & Biopharmaceutical Units", "primary_hub": "Bengaluru Karnataka / Puducherry / Chennai"},
    {"name": "Sequent Scientific Limited", "domain": "sequent.in", "sector": "Veterinary APIs, Formulations & Animal Healthcare Products", "primary_hub": "Mangaluru Panambur / Tarapur / Vizag"},
    {"name": "Indoco Remedies Limited", "domain": "indoco.com", "sector": "Sterile Ophthalmic Formulations, Oral Dosages & APIs", "primary_hub": "Verna Salcete Goa / Rabale Navi Mumbai / Baddi"},
    {"name": "FDC Limited", "domain": "fdcindia.com", "sector": "Electral Oral Electrolytes, Bulk Drugs & Ophthalmic Solutions", "primary_hub": "Waluj Aurangabad / Roha / Baddi"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india|industries)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_15 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_15.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 15 Clean Companies: {len(final_batch_15)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch15_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 15 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-14)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_15_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_15[:50]):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == min(len(final_batch_15), 50) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {min(len(final_batch_15), 50)} accounts.")
