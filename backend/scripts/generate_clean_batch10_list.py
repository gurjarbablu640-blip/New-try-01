"""Curates Batch 10 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Used: {len(all_used_names)}")

CANDIDATE_POOL = [
    # Commercial Vehicles, Electric Buses & Specialty Transportation
    {"name": "Olectra Greentech Limited", "domain": "olectra.com", "sector": "Electric Buses, Commercial EVs & Polymer Insulators", "primary_hub": "Hyderabad Cherlapally"},
    {"name": "SML Isuzu Limited", "domain": "smlisuzu.com", "sector": "Commercial Trucks, Buses & Special Purpose Vehicles", "primary_hub": "Nawanshahr Punjab Asron"},
    {"name": "Bharat Gears Limited", "domain": "bharatgears.com", "sector": "Automotive Transmission Gears, Shafts & Crown Wheels", "primary_hub": "Mumbra Thane / Faridabad"},
    {"name": "Automotive Stampings and Assemblies Limited", "domain": "autostampings.com", "sector": "Sheet Metal Stampings & Welded Structural Assemblies", "primary_hub": "Pune Bhosari / Pantnagar"},
    {"name": "Munjal Showa Limited", "domain": "munjalshowa.net", "sector": "Shock Absorbers, Struts & Window Regulators", "primary_hub": "Gurugram / Manesar"},

    # High Tensile Steel Wire, Wire Ropes & Bead Wires
    {"name": "Usha Martin Limited", "domain": "ushamartin.com", "sector": "Specialty Wire Ropes, Strands & Pre-Stressed Concrete Wires", "primary_hub": "Ranchi Tatisilwai / Hoshiarpur"},
    {"name": "Rajratan Global Wire Limited", "domain": "rajratan.co.in", "sector": "Automotive Tire Bead Wire & High Carbon Steel Wires", "primary_hub": "Pithampur Madhya Pradesh"},
    {"name": "Bharat Wire Ropes Limited", "domain": "bharatwireropes.com", "sector": "Steel Wire Ropes for Mining, Ports & Cranes", "primary_hub": "Chalisgaon Jalgaon Maharashtra"},
    {"name": "D.P. Wires Limited", "domain": "dpwires.co.in", "sector": "LRPC Strands, Spring Steel Wires & Induction Tempered Wires", "primary_hub": "Ratlam Madhya Pradesh"},
    {"name": "Sunflag Iron and Steel Company Limited", "domain": "sunflagsteel.com", "sector": "Special Alloy Steels, Rolled Bars & Blooms", "primary_hub": "Bhandara Maharashtra Warthi"},

    # Specialty Fluorochemicals, Electrolytes & Bromine
    {"name": "Epigral Limited", "domain": "epigral.com", "sector": "Chlorinated Polyvinyl Chloride & Chlor-Alkali Chemicals", "primary_hub": "Dahej Gujarat"},
    {"name": "Tatva Chintan Pharma Chem Limited", "domain": "tatvachintan.com", "sector": "Structure Directing Agents, Phase Transfer Catalysts & Electrolytes", "primary_hub": "Ankleshwar / Dahej"},
    {"name": "Laxmi Organic Industries Limited", "domain": "laxmi.com", "sector": "Acetyl Intermediates & Diketene Specialty Derivatives", "primary_hub": "Mahad Maharashtra"},
    {"name": "Archean Chemical Industries Limited", "domain": "archeanchemicals.com", "sector": "Industrial Bromine, Industrial Salt & Sulphate of Potash", "primary_hub": "Hajipir Kutch Gujarat"},
    {"name": "Kronox Lab Sciences Limited", "domain": "kronoxlabsciences.com", "sector": "High Purity Specialty Fine Chemicals & Reagents", "primary_hub": "Padra Vadodara"},

    # Industrial Packaging, Barrels & Specialty Bottles
    {"name": "Manjushree Technopack Limited", "domain": "manjushreeindia.com", "sector": "Rigid Plastic Packaging & Automated Injection Blow Moulding", "primary_hub": "Bengaluru Bidadi / Baddi"},
    {"name": "EPL Limited", "domain": "eplglobal.com", "sector": "Laminated Plastic Tubes & Barrier Packaging", "primary_hub": "Vasind Maharashtra / Wada"},
    {"name": "Mold-Tek Packaging Limited", "domain": "moldtekpackaging.com", "sector": "In-Mold Labeling Injection Moulded Pails & Containers", "primary_hub": "Hyderabad Annaram / Daman"},
    {"name": "Polycon International Limited", "domain": "polycon.co.in", "sector": "Blow Moulded Industrial Water Tanks & Rotomoulded Drums", "primary_hub": "Jaipur Sitapura"},

    # Heavy Fabrication & Process Tanks
    {"name": "Pennar Engineered Building Systems Limited", "domain": "pebs.in", "sector": "Pre-Engineered Steel Buildings & Heavy Structural Framing", "primary_hub": "Sadashivpet Sangareddy Telangana"},
    {"name": "Zuari Agro Chemicals Limited", "domain": "adityabirlachemicals.com", "sector": "Industrial Phosphatic Fertilizers & Complex Nutrients", "primary_hub": "Zuarinagar Sancoale Goa"},
    {"name": "Paradeep Phosphates Limited", "domain": "paradeepphosphates.com", "sector": "Sulphuric Acid Plants & Phosphoric Acid Complexes", "primary_hub": "Paradeep Odisha / Zuarinagar"},
    {"name": "Coromandel International Limited", "domain": "coromandel.biz", "sector": "Phosphatic Fertilisers & Crop Protection Chemicals", "primary_hub": "Visakhapatnam / Ennore"},

    # Industrial Fasteners & Precision Cold Heading
    {"name": "Kovai Fasteners Private Limited", "domain": "kovaifasteners.com", "sector": "Cold Forged High Tensile Bolts & Specialized Studs", "primary_hub": "Coimbatore Sulur"},
    {"name": "Deepak Fasteners Limited", "domain": "unbrako.com", "sector": "Industrial Socket Screws & Structural Bolting Assemblies", "primary_hub": "Ludhiana Focal Point / Indore"},

    # Solar PV Module, Cell & Clean Energy Equipment Manufacturing
    {"name": "Waaree Energies Limited", "domain": "waaree.com", "sector": "High-Efficiency Solar PV Modules & Solar Cells", "primary_hub": "Surat / Chikhli Gujarat"},
    {"name": "Vikram Solar Limited", "domain": "vikramsolar.com", "sector": "Tier-1 Solar PV Modules & EPC Complexes", "primary_hub": "Falta SEZ West Bengal / Oragadam"},
    {"name": "Goldi Solar Private Limited", "domain": "goldisolar.com", "sector": "Monocrystalline Solar Modules & Strings", "primary_hub": "Navsari Gujarat / Pipodara"},
    {"name": "Servotech Power Systems Limited", "domain": "servotech.in", "sector": "EV Fast Chargers & Solar Inverters", "primary_hub": "Bhatinda / Sonipat"},

    # High-Volume Active Pharmaceutical Ingredients (API) & Intermediates
    {"name": "Neuland Laboratories Limited", "domain": "neulandlabs.com", "sector": "Custom Synthesis APIs & Complex Peptides", "primary_hub": "Bonthapally / Pashamylaram Hyderabad"},
    {"name": "Solara Active Pharma Sciences Limited", "domain": "solara.co.in", "sector": "Polymer Based APIs & High-Volume Intermediates", "primary_hub": "Cuddalore / Mangaluru"},
    {"name": "Unichem Laboratories Limited", "domain": "unichemlabs.com", "sector": "Active Pharmaceutical Ingredients & Formulations", "primary_hub": "Pithampur / Roha"},
    {"name": "Windlas Biotech Limited", "domain": "windlasbiotech.com", "sector": "Contract Dosage Manufacturing & Sterile Liquids", "primary_hub": "Dehradun Uttarakhand"},
    {"name": "Innova Captab Limited", "domain": "innovacaptab.com", "sector": "Dry Syrups, Solid Orals & Softgel Capsules", "primary_hub": "Baddi Himachal Pradesh"},
    {"name": "Blue Jet Healthcare Limited", "domain": "bluejethealthcare.com", "sector": "Contrast Media Intermediates & High-Purity APIs", "primary_hub": "Shahad / Ambernath"},
    {"name": "Concord Biotech Limited", "domain": "concordbiotech.com", "sector": "Fermentation APIs & Immunosuppressants", "primary_hub": "Dholka Ahmedabad / Valthera"},

    # Agrochemicals, Technical Actives & Crop Nutrition
    {"name": "Insecticides (India) Limited", "domain": "insecticidesindia.com", "sector": "Technical Grade Pesticides & Crop Protection", "primary_hub": "Chopanki Bhiwadi / Dahej"},
    {"name": "Dhanuka Agritech Limited", "domain": "dhanuka.com", "sector": "Emulsifiable Concentrates & Agrochemical Formulations", "primary_hub": "Sanand Gujarat / Keshwana"},
    {"name": "Bharat Rasayan Limited", "domain": "bharatgroup.co.in", "sector": "Technical Grade Insecticides & Intermediates", "primary_hub": "Dahej Gujarat / Rohtak"},
    {"name": "Best Agrolife Limited", "domain": "bestagrolife.com", "sector": "Specialized Herbicides & Integrated Agrochem Complexes", "primary_hub": "Gajraula UP / Jammu"},
    {"name": "Heranba Industries Limited", "domain": "heranba.co.in", "sector": "Synthetic Pyrethroids & Technical Actives", "primary_hub": "Vapi Gujarat / Sarigam"},
    {"name": "Dharmaj Crop Guard Limited", "domain": "dharmajcrop.com", "sector": "Agrochemical Formulations, Granules & Micro-Nutrients", "primary_hub": "Saykha Bharuch Gujarat"},

    # Precision Industrial Bearings & Needle Rollers
    {"name": "Timken India Limited", "domain": "timken.com", "sector": "Tapered Roller Bearings & Railway Cartridge Bearings", "primary_hub": "Jamshedpur / Bharuch"},
    {"name": "Schaeffler India Limited", "domain": "schaeffler.co.in", "sector": "High Precision Ball Bearings & Engine Components", "primary_hub": "Maneja Vadodara / Talegaon"},
    {"name": "NRB Bearings Limited", "domain": "nrbbearings.com", "sector": "Needle Roller Bearings & Cylindrical Roller Bearings", "primary_hub": "Thane / Waluj / Hyderabad"},
    {"name": "Austin Engineering Company Limited", "domain": "aec.com", "sector": "All Types of Industrial Roller & Ball Bearings", "primary_hub": "Junagadh Gujarat"},

    # Specialized Technical Glassware & Tableware
    {"name": "Borosil Limited", "domain": "borosil.com", "sector": "Laboratory Glassware, Pharmaceutical Vials & Consumer Glass", "primary_hub": "Bharuch / Tarapur"},
    {"name": "La Opala RG Limited", "domain": "laopala.in", "sector": "Opal Glass Tableware & Lead Crystal Glass", "primary_hub": "Madhupur Jharkhand / Sitarganj"},
    {"name": "Haldyn Glass Limited", "domain": "haldynglass.com", "sector": "Soda Lime Flint Glass Bottles & Vials", "primary_hub": "Vadodara Gothda"},

    # Industrial Printing Inks & Specialty Resins
    {"name": "DIC India Limited", "domain": "dic.co.in", "sector": "News Inks, Gravure Packaging Inks & Lamination Adhesives", "primary_hub": "Kolkata / Noida / Saykha"},
    {"name": "TRF Limited", "domain": "trf.co.in", "sector": "Bulk Material Handling Equipment, Crushers & Screeners", "primary_hub": "Jamshedpur Burmamines"},

    # Industrial Packaging, Corrugated Boxes & Paper Mills
    {"name": "Star Paper Mills Limited", "domain": "starpapers.com", "sector": "Industrial Packaging Paper & Bleached Kraft Paper", "primary_hub": "Saharanpur Uttar Pradesh"},
    {"name": "Emami Paper Mills Limited", "domain": "emamipaper.in", "sector": "Multi-Layer Packaging Board & Newsprint Mills", "primary_hub": "Balasore Odisha"},
    {"name": "Genus Paper and Boards Limited", "domain": "genuspaper.com", "sector": "Kraft Paper, Duplex Board & Corrugated Sheets", "primary_hub": "Moradabad UP"},
    {"name": "N R Agarwal Industries Limited", "domain": "nrail.com", "sector": "Duplex Packaging Boards & Writing Paper", "primary_hub": "Vapi Gujarat"},
    {"name": "Worth Peripherals Limited", "domain": "worthindia.com", "sector": "Corrugated Boxes & Automated Cartoning Machinery", "primary_hub": "Pithampur Madhya Pradesh"},

    # Protective Safety Equipment & Industrial Moulding
    {"name": "Studds Accessories Limited", "domain": "studds.com", "sector": "Motorcycle Helmets & Injection Moulded Shells", "primary_hub": "Faridabad Haryana"},
    {"name": "Steelbird Hi-Tech India Limited", "domain": "steelbirdhelmet.com", "sector": "Industrial Safety Helmets & Polycarbonate Visors", "primary_hub": "Nalagarh Himachal Pradesh"},

    # Precision Yarn & Compact Textile Mills
    {"name": "Ambika Cotton Mills Limited", "domain": "acmlindia.com", "sector": "Supima & Compact Cotton Yarn Mills", "primary_hub": "Dindigul Tamil Nadu"},
    {"name": "Bannari Amman Spinning Mills Limited", "domain": "bannarimills.com", "sector": "Automated Spinning, Weaving & Processing Units", "primary_hub": "Dindigul / Coimbatore"},
    {"name": "Precot Limited", "domain": "precot.com", "sector": "Combed Cotton Yarn, Thread & Non-Woven Spunlace", "primary_hub": "Coimbatore Kanjikode"},
    {"name": "Rajapalayam Mills Limited", "domain": "rajapalayammills.co.in", "sector": "High Count Compact Yarn & Open-End Yarn", "primary_hub": "Rajapalayam Tamil Nadu"},

    # Industrial Process Valves, Skids & Heavy Pumping
    {"name": "Advance Valves Private Limited", "domain": "advancevalves.com", "sector": "Dual Plate Check Valves & Triple Eccentric Butterfly Valves", "primary_hub": "Noida Phase II / Gagret"},
    {"name": "Intervalve Poonawalla Limited", "domain": "poonawallagroup.com", "sector": "Industrial Butterfly Valves & Pneumatic Actuators", "primary_hub": "Pune Vanaz"},
    {"name": "Fouress Engineering (India) Limited", "domain": "fouressindia.com", "sector": "Large Diameter Butterfly Valves & Hydro Turbine Equipment", "primary_hub": "Bengaluru Hosur Road / Thane"},
    {"name": "Enpro Industries Private Limited", "domain": "enproindia.com", "sector": "Skid Mounted Process Systems & Lube Oil Packages", "primary_hub": "Pune Bhosari"},
    {"name": "Akay Industries Private Limited", "domain": "akayindustries.com", "sector": "API 610 Centrifugal Heavy Process Pumps", "primary_hub": "Hubballi Karnataka"},
    {"name": "Steel Strong Valves Private Limited", "domain": "steelstrong.com", "sector": "High Pressure Gate, Globe & Swing Check Valves", "primary_hub": "Sanand Ahmedabad"},
]

def normalize_corp(name: str) -> str:
    cleaned = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|solutions|industries|india)\b", "", name.lower(), flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", cleaned)

used_normalized = {normalize_corp(n): n for n in all_used_names}

filtered = []
for cand in CANDIDATE_POOL:
    cand_name = cand["name"]
    cand_norm = normalize_corp(cand_name)
    if not cand_norm or len(cand_norm) < 3:
        continue
    if cand_norm in used_normalized:
        print(f"Duplicate (normalized): '{cand_name}' matches '{used_normalized[cand_norm]}'")
        continue
    filtered.append(cand)
    used_normalized[cand_norm] = cand_name

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

# Select up to 50
batch_10 = filtered[:50]

out_code = f'"""Curated Batch 10 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5, 6, 7, 8, 9)."""\n'
out_code += "from typing import Dict, List\n\n"
out_code += "BATCH_10_COMPANIES: List[Dict[str, str]] = " + json.dumps(batch_10, indent=4) + "\n"

target_path = os.path.join(os.path.dirname(__file__), "prepare_batch10_company_list.py")
with open(target_path, "w", encoding="utf-8") as f:
    f.write(out_code)

print(f"Wrote {len(batch_10)} companies to {target_path}")
