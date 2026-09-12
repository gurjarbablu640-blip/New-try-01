"""Curates Batch 18 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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
from scripts.prepare_batch15_company_list import BATCH_15_COMPANIES
from scripts.prepare_batch16_company_list import BATCH_16_COMPANIES
from scripts.prepare_batch17_company_list import BATCH_17_COMPANIES

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
for c in BATCH_15_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_16_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_17_COMPANIES:
    all_used_names.add(c["name"].lower().strip())

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-17): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Group 1: Medical Devices, Consumables & Labware
    {"name": "Tarsons Products Limited", "domain": "tarsons.com", "sector": "Plastic Labware, Centrifuge Tubes, Pipette Tips & PCR Consumables", "primary_hub": "Jalan Industrial Complex Howrah West Bengal / Panchla"},
    {"name": "Nectar Lifesciences Limited", "domain": "neclife.com", "sector": "Cephalosporin APIs, Sterile Injectable Bulk Drugs & Hard Gelatin Capsules", "primary_hub": "Derabassi Mohali Punjab / Baddi HP"},
    {"name": "Kopran Limited", "domain": "kopran.com", "sector": "Semi-Synthetic Penicillins, Active Pharmaceutical Ingredients & Formulations", "primary_hub": "Mahad Raigad Maharashtra / Panoli Gujarat"},

    # Group 2: Jute Packaging & Industrial Geo-Textiles
    {"name": "Cheviot Company Limited", "domain": "groupcheviot.net", "sector": "Jute Fabrics, Sacking Bags, Technical Jute Yarns & Geotextiles", "primary_hub": "Budge Budge South 24 Parganas West Bengal"},
    {"name": "Gloster Limited", "domain": "glosterjute.com", "sector": "Jute Geotextiles, Treated Industrial Hessian & Decorative Jute Fabrics", "primary_hub": "Bauria Howrah West Bengal"},
    {"name": "Ludlow Jute & Specialities Limited", "domain": "ludlowjute.com", "sector": "Jute Sacking, Webbing, High Grade Jute Yarns & Soil Savers", "primary_hub": "Chengail Howrah West Bengal"},

    # Group 3: Packaged Foods & Specialty Agro Products
    {"name": "Tasty Bite Eatables Limited", "domain": "tastybite.co.in", "sector": "Ready-to-Eat Prepared Meals, Frozen Sauces & Specialty Organic Foods", "primary_hub": "Bhandgaon Pune Maharashtra"},
    {"name": "Sheetal Cool Products Limited", "domain": "sheetalcool.com", "sector": "Sheetal Brand Ice Creams, Frozen Foods, Milk & Namkeen", "primary_hub": "Amreli Gujarat"},
    {"name": "Sarveshwar Foods Limited", "domain": "sarveshwarfoods.com", "sector": "Organic Basmati Rice Milling, Packaging & Parboiling Plants", "primary_hub": "Bari Brahmana Jammu J&K"},
    {"name": "Mishtann Foods Limited", "domain": "mishtann.com", "sector": "Agro Food Processing, Basmati Rice Sortex & Grain Value Addition", "primary_hub": "Himmatnagar Sabarkantha Gujarat"},
    {"name": "Umang Dairies Limited", "domain": "umangdairies.com", "sector": "White Magik Dairy Creamer, Skimmed Milk Powder & Butter Oil", "primary_hub": "Gajraula Amroha Uttar Pradesh"},
    {"name": "Milkfood Limited", "domain": "milkfoodltd.com", "sector": "Pure Ghee, Casein, Demineralized Whey Powder & Dairy Products", "primary_hub": "Bahadurgarh Patiala Punjab / Moradabad UP"},
    {"name": "Annapurna Swadisht Limited", "domain": "annapurnasnacks.in", "sector": "Pellet Extruded Snacks, Fryums, Potato Chips & Confectionery", "primary_hub": "Asansol Paschim Bardhaman West Bengal"},

    # Group 4: Specialty Yarns & Spinning Mills
    {"name": "Super Spinning Mills Limited", "domain": "superspinning.com", "sector": "Combed Cotton Yarns, Compact Gassed Yarns & Open End Yarns", "primary_hub": "Kotnur Hindupur AP / Coimbatore Tamil Nadu"},
    {"name": "Loyal Textile Mills Limited", "domain": "loyaltextiles.com", "sector": "Ring Spun Yarns, Knitted Fabrics & Industrial Protective Garments", "primary_hub": "Kovilpatti Tuticorin / Sattur Tamil Nadu"},
    {"name": "Nahar Spinning Mills Limited", "domain": "owmnahar.com", "sector": "100% Cotton & Blended Spun Yarns, Knitted Fabric Garments", "primary_hub": "Ludhiana Punjab / Mandideep MP / Lalru"},

    # Group 5: Active Telecom, Electronics & Power Systems
    {"name": "Smartlink Holdings Limited", "domain": "smartlinkholdings.com", "sector": "Active & Passive Networking Products, Structured Cabling & Routers", "primary_hub": "Verna Salcete Goa"},
    {"name": "Aplab Limited", "domain": "aplab.com", "sector": "Power Electronic Equipment, UPS Systems, Telemetry & Inverters", "primary_hub": "Thane Maharashtra / Navi Mumbai / Pune"},
    {"name": "McNally Bharat Engineering Company Limited", "domain": "mcnallybharat.com", "sector": "Turnkey Mineral Beneficiation Plants, Crushing & Screening Units", "primary_hub": "Kumardhubi Dhanbad Jharkhand / Asansol"},

    # Group 6: Specialty Polymers & Recycled Compounds
    {"name": "Shish Industries Limited", "domain": "shishindustries.com", "sector": "Corrugated Polypropylene Sheets, Insulation Materials & Strapping Rolls", "primary_hub": "Surat Gujarat"},
    {"name": "Vikas Lifecare Limited", "domain": "vikaslifecare.com", "sector": "Recycled Polymer Compounds, Plastic Additives & EVA Masterbatches", "primary_hub": "Shahjahanpur Rajasthan / Noida UP"},

    # Group 7: Bulk Drugs, Formulations & Active Ingredients
    {"name": "Venus Remedies Limited", "domain": "venusremedies.com", "sector": "Injectables, Cephalosporins, Carbapenems & Oncology Formulations", "primary_hub": "Panchkula Haryana / Baddi Himachal Pradesh"},
    {"name": "Albert David Limited", "domain": "albertdavidindia.com", "sector": "Placentrex, Large Volume Parenterals & Sterile Infusions", "primary_hub": "Kolkata West Bengal / Ghaziabad UP / Mandideep MP"},
    {"name": "SMS Lifesciences India Limited", "domain": "smslife.in", "sector": "Ranitidine, Cimetidine & Active Pharmaceutical Ingredients", "primary_hub": "Bollaram / Jeedimetla Hyderabad Telangana"},
    {"name": "Zim Laboratories Limited", "domain": "zimlab.in", "sector": "Oral Thin Films, Pellets, Taste Masked Granules & Dry Suspensions", "primary_hub": "Kalmeshwar Nagpur Maharashtra"},
    {"name": "Syncom Formulations (India) Limited", "domain": "syncomformulations.com", "sector": "Tablets, Capsules, Liquids, Injections & Dry Syrups Formulations", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Wanbury Limited", "domain": "wanbury.com", "sector": "Metformin Active Pharmaceutical Ingredients & Formulations", "primary_hub": "Patalganga Raigad / Tanuku AP / Turbhe Navi Mumbai"},
    {"name": "Jenburkt Pharmaceuticals Limited", "domain": "jenburkt.com", "sector": "Therapeutic Finished Formulations & Prescription Healthcare Products", "primary_hub": "Sihor Bhavnagar Gujarat"},
    {"name": "Bal Pharma Limited", "domain": "balpharma.com", "sector": "Gliclazide APIs, Finished Dosage Formulations & Intravenous Fluids", "primary_hub": "Bommasandra Bengaluru / Rudrapur / Udaipur"},

    # Group 8: Solar Power, Paperboards & Precision Wheels
    {"name": "KPI Green Energy Limited", "domain": "kpigreenenergy.com", "sector": "Solar Power Plants, Hybrid Renewable Projects & Substation Transformers", "primary_hub": "Amod Bharuch Gujarat"},
    {"name": "Magnum Ventures Limited", "domain": "magnumventures.in", "sector": "Writing Papers, Newsprint, Duplex Paper Boards & Printing Inks", "primary_hub": "Sahibabad Ghaziabad Uttar Pradesh"},
    {"name": "Malu Paper Mills Limited", "domain": "malupaper.com", "sector": "Newsprint, Kraft Paper & Writing/Printing Paper Manufacturing", "primary_hub": "Saoner Nagpur Maharashtra"},
    {"name": "Enkei Wheels (India) Limited", "domain": "enkei.in", "sector": "Aluminium Alloy Wheels for Four-Wheelers & Two-Wheelers", "primary_hub": "Shikrapur Shirur Pune Maharashtra"},
    {"name": "JMT Auto Limited", "domain": "jmtauto.com", "sector": "Automotive Ring Gears, Pinions, Carrier Assemblies & Heavy Machining", "primary_hub": "Adityapur Jamshedpur Jharkhand / Dharuhera"},

    # Group 9: Micro-Irrigation, Agricultural Pumps & Electricals
    {"name": "Jain Irrigation Systems Limited", "domain": "jains.com", "sector": "Drip Irrigation Systems, PVC Pipes, Solar Pumping & Food Processing Plants", "primary_hub": "Bambhori Jalgaon Maharashtra / Alwar / Vadodara"},
    {"name": "Signet Industries Limited", "domain": "groupsignet.com", "sector": "Micro Irrigation Systems, Sprinkler Pipes, HDPE Pipes & Plastic Moulding", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Finolex Plasson Industries Private Limited", "domain": "finolexplasson.com", "sector": "Drip Irrigation Laterals, Screen Filters & Agricultural Automation", "primary_hub": "Urse Talegaon Pune Maharashtra"},
    {"name": "CRI Pumps Private Limited", "domain": "crigroups.com", "sector": "Agricultural Submersible Pumps, Sewage Pumps & Solar Pumping Systems", "primary_hub": "Saravanampatti Coimbatore Tamil Nadu"},
    {"name": "Falcon Pumps Private Limited", "domain": "falconpumps.com", "sector": "Submersible Pumps, Openwell Pumps & Borewell Column Pipes", "primary_hub": "Vavdi Rajkot Gujarat"},
    {"name": "Texmo Industries", "domain": "taropumps.com", "sector": "Taro Brand Submersible Pumps, Monobloc Pumps & Agricultural Motors", "primary_hub": "Mettupalayam Road Coimbatore Tamil Nadu"},
    {"name": "LAPP India Private Limited", "domain": "lappindia.lappgroup.com", "sector": "ÖLFLEX Industrial Flexible Cables, Solar Cables & Automation Harnesses", "primary_hub": "Jigani Bengaluru Karnataka / Pilukhedi Bhopal MP"},
    {"name": "Panasonic Life Solutions India Private Limited", "domain": "ls-in.panasonic.com", "sector": "Anchor Modular Electrical Switches, Wires, Switchgear & Lighting", "primary_hub": "Daman / Haridwar / Kutch Gujarat / Sri City"},
    {"name": "Goldmedal Electricals Private Limited", "domain": "goldmedalindia.com", "sector": "Modular Switches, LED Lighting Luminaires, Wires & Home Automation", "primary_hub": "Bhiwadi Rajasthan / Vijayawada AP"},

    # Group 10: Heavy Farm Implements, Commercial Vehicles & Compressed Air
    {"name": "Tirth Agro Technology Private Limited", "domain": "shaktimanagro.com", "sector": "Shaktiman Brand Rotavators, Harvesters & Precision Rotary Tillers", "primary_hub": "Bhunava Gondal Rajkot Gujarat"},
    {"name": "Beri Udyog Private Limited", "domain": "fieldking.com", "sector": "Fieldking Brand Rotary Tillers, Disc Harrows & Combine Harvesters", "primary_hub": "Karnal Haryana"},
    {"name": "LEMKEN India Agro Equipment Private Limited", "domain": "lemken.com", "sector": "Hydraulic Reversible Plough, Cultivators & Soil Preparation Implements", "primary_hub": "Nagpur Butibori Maharashtra"},
    {"name": "CNH Industrial (India) Private Limited", "domain": "cnhindustrial.com", "sector": "New Holland Tractors, Combine Harvesters & Sugarcane Harvesters", "primary_hub": "Greater Noida Uttar Pradesh / Pune"},
    {"name": "CLAAS India Private Limited", "domain": "claas.co.in", "sector": "CROP TIGER Combine Harvesters, Forage Harvesters & Agricultural Headers", "primary_hub": "Morinda Rupnagar Punjab"},
    {"name": "Hyva India Private Limited", "domain": "hyva.com", "sector": "Hydraulic Front End Cylinders, Tipping Systems & Waste Handling Equipment", "primary_hub": "Navi Mumbai / Pune Chakan / Jamshedpur"},
    {"name": "VE Commercial Vehicles Limited", "domain": "vecv.in", "sector": "Eicher Heavy Commercial Trucks, Bus Chassis & Medium Duty Diesel Engines", "primary_hub": "Pithampur Dhar MP / Baggad / Thane"},
    {"name": "Anest Iwata Motherson Private Limited", "domain": "aimcompressors.com", "sector": "Reciprocating Air Compressors, Oil-Free Compressors & Paint Spray Guns", "primary_hub": "Greater Noida UP / Sanand Gujarat"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india|industries)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_18 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_18.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 18 Clean Companies: {len(final_batch_18)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch18_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 18 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-17)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_18_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_18[:50]):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == min(len(final_batch_18), 50) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {min(len(final_batch_18), 50)} accounts.")
