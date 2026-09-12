import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load all used companies across all previous batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

used = set()
for c in BATCH_100_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_3_COMPANIES:
    used.add(c["name"].lower().strip())

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            used.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            used.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Used: {len(used)}")

# 2. Candidate Pool for Batch 4 (Textiles, Cement, Mining, Paper, Sugar/Bio-ethanol, Bearings)
CANDIDATE_POOL = [
    # Precision Bearings & Power Transmission
    {"name": "Timken India Limited", "domain": "timken.com", "sector": "Tapered Roller Bearings & Mechanical Power Transmission", "primary_hub": "Jamshedpur / Bharuch"},
    {"name": "Schaeffler India Limited", "domain": "schaeffler.co.in", "sector": "Industrial Bearings & Precision Engine Components", "primary_hub": "Maneja Vadodara / Savli / Talegaon"},
    {"name": "NRB Bearings Limited", "domain": "nrbbearings.com", "sector": "Needle & Cylindrical Roller Bearings", "primary_hub": "Thane / Waluj / Hyderabad / Pantnagar"},
    {"name": "Menon Bearings Limited", "domain": "menonbearings.com", "sector": "Engine Bearings, Bushings & Thrust Washers", "primary_hub": "Kolhapur Gokul Shirgaon"},

    # Technical Textiles & Industrial Fabrics
    {"name": "Garware Technical Fibres Limited", "domain": "garwarefibres.com", "sector": "Technical Textiles, Aquaculture Nets & Geosynthetics", "primary_hub": "Pune / Wai Satara"},
    {"name": "Arvind Limited", "domain": "arvind.com", "sector": "Advanced Materials, Technical Textiles & Composites", "primary_hub": "Santej Ahmedabad / Naroda"},
    {"name": "Trident Limited", "domain": "tridentindia.com", "sector": "Yarn, Terry Towels & Wheat Straw Paper", "primary_hub": "Barnala / Budhni Sehore"},
    {"name": "Vardhman Textiles Limited", "domain": "vardhman.com", "sector": "Yarns, Processed Fabrics & Special Steel", "primary_hub": "Baddi / Mandideep / Ludhiana"},
    {"name": "KPR Mill Limited", "domain": "kprmilllimited.com", "sector": "Knitted Apparel, Cotton Yarn & Sugar/Ethanol", "primary_hub": "Coimbatore / Perundurai / Alambadi"},
    {"name": "Welspun Living Limited", "domain": "welspunliving.com", "sector": "Home Textiles & Advanced Flooring", "primary_hub": "Anjar Kutch / Vapi"},

    # Cement & Heavy Building Materials
    {"name": "UltraTech Cement Limited", "domain": "ultratechcement.com", "sector": "Grey Cement, Ready Mix Concrete & White Cement", "primary_hub": "Kotputli / Awarpur / Tadipatri"},
    {"name": "Ambuja Cements Limited", "domain": "ambujacement.com", "sector": "Clinker, Portland Pozzolana Cement & Microfine Cements", "primary_hub": "Ambujanagar Kodinar / Bhatapara / Darlaghat"},
    {"name": "ACC Limited", "domain": "acclimited.com", "sector": "Portland Cement & Ready Mix Concrete", "primary_hub": "Wadi Gulbarga / Jamul Durg / Chanda"},
    {"name": "Shree Cement Limited", "domain": "shreecement.com", "sector": "Cement Clinker & Synthetic Gypsum", "primary_hub": "Beawar / Ras Pali / Baloda Bazar"},
    {"name": "Dalmia Bharat Limited", "domain": "dalmiabhart.com", "sector": "Super Specialty Cements & Oil Well Cement", "primary_hub": "Dalmiapuram / Belgaum / Rajgangpur"},
    {"name": "The Ramco Cements Limited", "domain": "ramcocements.in", "sector": "High Grade Portland Cements & Dry Mortar", "primary_hub": "Ramasamy Raja Nagar / Ariyalur / Jayanthipuram"},
    {"name": "JK Cement Limited", "domain": "jkcement.com", "sector": "Grey Cement & White Cement Formulations", "primary_hub": "Nimbahera / Mangrol / Muddapur / Aligarh"},
    {"name": "Star Cement Limited", "domain": "starcement.co.in", "sector": "Portland Pozzolana Cement & Clinker", "primary_hub": "Lumshnong Meghalaya / Guwahati / Siliguri"},
    {"name": "Nuvoco Vistas Corporation Limited", "domain": "nuvoco.com", "sector": "Construction Materials & Specialized Concretes", "primary_hub": "Arasmeta / Risda / Chittorgarh"},

    # Mining, Mineral Processing & Industrial Metals
    {"name": "NMDC Limited", "domain": "nmdc.co.in", "sector": "Iron Ore Mining & Pelletization Plants", "primary_hub": "Bailadila / Donimalai / Nagarnar"},
    {"name": "MOIL Limited", "domain": "moil.nic.in", "sector": "Manganese Ore Mining & Electrolytic Manganese Dioxide", "primary_hub": "Balaghat / Nagpur / Dongri Buzurg"},
    {"name": "Gujarat Mineral Development Corporation Limited", "domain": "gmdcltd.com", "sector": "Lignite Mining, Bauxite & Fluorspar Beneficiation", "primary_hub": "Panandhro / Tadkeshwar / Ambaji"},
    {"name": "Hindustan Copper Limited", "domain": "hindustancopper.com", "sector": "Copper Cathodes, Continuous Cast Copper Wire Rods", "primary_hub": "Khetri Jhunjhunu / Malanjkhand Balaghat / Ghatsila"},

    # Paper, Pulp & Specialty Packaging Boards
    {"name": "JK Paper Limited", "domain": "jkpaper.com", "sector": "Copier Paper, Packaging Boards & Coated Paper", "primary_hub": "Rayagada Odisha / Songadh Surat / Sirpur Kaghaznagar"},
    {"name": "West Coast Paper Mills Limited", "domain": "westcoastpaper.com", "sector": "Printing, Writing & Duplex Packaging Board", "primary_hub": "Dandeli Uttara Kannada"},
    {"name": "Andhra Paper Limited", "domain": "andhrapaper.com", "sector": "Specialty Pulp, High Brightness Writing Paper", "primary_hub": "Rajahmundry / Kadiyam"},
    {"name": "Seshasayee Paper and Boards Limited", "domain": "spbltd.com", "sector": "Eco-Friendly Printing Paper & Packaging Boards", "primary_hub": "Erode / Tirunelveli"},
    {"name": "Century Textiles and Industries Limited", "domain": "centurytextind.com", "sector": "Pulp, Paper, Tissue & Century Rayon", "primary_hub": "Lalkuan Nainital / Kalyan"},

    # Sugar, Bio-Ethanol & Industrial Alcohol
    {"name": "Balrampur Chini Mills Limited", "domain": "chini.com", "sector": "Sugar Refining, Potable Alcohol & Fuel-Grade Bioethanol", "primary_hub": "Balrampur / Maizapur / Gularia"},
    {"name": "Shree Renuka Sugars Limited", "domain": "renukasugars.com", "sector": "Refined White Sugar, Fuel Ethanol & Bio-Electricity", "primary_hub": "Munoli Belagavi / Athani / Havalga"},
    {"name": "Triveni Engineering and Industries Limited", "domain": "trivenigroup.com", "sector": "Multi-Feed Distillery & Defense Gearboxes", "primary_hub": "Khatauli / Deoband / Sabitgarh / Mysuru"},
    {"name": "EID Parry (India) Limited", "domain": "eidparry.com", "sector": "Sugar Processing, Nutraceuticals & Ethanol", "primary_hub": "Nellikuppam Cuddalore / Pugalur / Haliyal"},
    {"name": "Dhampur Sugar Mills Limited", "domain": "dhampursugar.com", "sector": "Refined Sugar, Fuel Ethanol & Industrial Alcohol", "primary_hub": "Dhampur Bijnor / Asmoli"},

    # Industrial Pumps, Valves & Flow Control
    {"name": "KSB Limited", "domain": "ksb.com", "sector": "Submersible Pumps, Industrial Valves & Energy Systems", "primary_hub": "Pimpri Pune / Chinchwad / Khandala"},
    {"name": "Kirloskar Pneumatic Company Limited", "domain": "kirloskarpneumatic.com", "sector": "Air Compressors, Refrigeration & Transmission Gears", "primary_hub": "Hadapsar Pune / Saswad"},
    {"name": "Roto Pumps Limited", "domain": "rotopumps.com", "sector": "Progressive Cavity & Twin Screw Industrial Pumps", "primary_hub": "Greater Noida / Noida Phase II"},

    # Fasteners, Forgings & Precision Stamping
    {"name": "Sterling Tools Limited", "domain": "sterlingtools.com", "sector": "High Tensile Cold Forged Fasteners & EV Components", "primary_hub": "Faridabad / Bengaluru"},
    {"name": "Sundram Fasteners Limited", "domain": "sundram.com", "sector": "High Tensile Fasteners, Powertrain Components & Hot Forgings", "primary_hub": "Padi Chennai / Krishnapuram / Pondicherry"},
    {"name": "Sansera Engineering Limited", "domain": "sansera.in", "sector": "Precision Machined Forged Components & Aerospace Parts", "primary_hub": "Bidadi / Bommasandra / Chakan"},
    {"name": "Ramkrishna Forgings Limited", "domain": "ramkrishnaforgings.com", "sector": "Large Forgings, Front Axle Beams & Crankshafts", "primary_hub": "Jamshedpur / Saraikela Kharsawan"},
    {"name": "Happy Forgings Limited", "domain": "happyforgings.com", "sector": "Heavy Commercial Vehicle Crankshafts & Transmission Forgings", "primary_hub": "Ludhiana Kanganwal"},
    {"name": "MM Forgings Limited", "domain": "mmforgings.com", "sector": "Steel Forgings & Precision Machined Auto Components", "primary_hub": "Singampunari / Viralimalai / Karai"},

    # Auto Ancillary Electricals & Lighting
    {"name": "Lumax Industries Limited", "domain": "lumaxworld.in", "sector": "Automotive Lighting Systems & Headlamps", "primary_hub": "Dharuhera / Chakan / Bawal / Sanand"},
    {"name": "Minda Corporation Limited", "domain": "sparkminda.com", "sector": "Electronic Security Systems, Die Casting & Wiring Harnesses", "primary_hub": "Greater Noida / Pune / Pantnagar"},
    {"name": "Pricol Limited", "domain": "pricol.com", "sector": "Driver Information Systems, Sensors & Telematics", "primary_hub": "Coimbatore / Manesar / Pune / Sriperumbudur"},
    {"name": "Suprajit Engineering Limited", "domain": "suprajit.com", "sector": "Mechanical Control Cables, Halogen Lamps & Actuators", "primary_hub": "Bommasandra Bengaluru / Chakan / Manesar / Pantnagar"},

    # Capital Equipment & Machine Tools
    {"name": "Jyoti CNC Automation Limited", "domain": "jyoti.co.in", "sector": "CNC Turning Centers & 5-Axis Machining Centers", "primary_hub": "Metoda Rajkot"},
    {"name": "HMT Limited", "domain": "hmtindia.com", "sector": "Machine Tools, Die Casting & Special Purpose Machines", "primary_hub": "Bengaluru / Pinjore / Kalamassery"},
    {"name": "Kennametal India Limited", "domain": "kennametal.com", "sector": "Tungsten Carbide Tooling & Wear Solutions", "primary_hub": "Bengaluru Yeshwantpur"},

    # Industrial Packaging, Cold Rolled Steel & Inorganic Chemicals
    {"name": "Godrej Industries Limited", "domain": "godrejindustries.com", "sector": "Oleochemicals, Fatty Alcohols & Glycerin", "primary_hub": "Valia Bharuch / Ambernath"},
    {"name": "DCW Limited", "domain": "dcwltd.com", "sector": "Caustic Soda, Synthetic Rutile & PVC Resins", "primary_hub": "Sahupuram Thoothukudi"},
    {"name": "GHCL Limited", "domain": "ghcl.co.in", "sector": "Soda Ash, Industrial Salt & Refined Bicarbonate", "primary_hub": "Sutrapada Junagadh"},
    {"name": "Jindal Poly Films Limited", "domain": "jindalpoly.com", "sector": "BOPP Films & Metallized Packaging Substrates", "primary_hub": "Nashik Igatpuri"},
    {"name": "Huhtamaki India Limited", "domain": "huhtamaki.com", "sector": "Specialty Flexible Food & Pharma Packaging", "primary_hub": "Silvassa / Khopoli / Rudrapur"},
    {"name": "Mold-Tek Packaging Limited", "domain": "moldtekpackaging.com", "sector": "Rigid Plastic Packaging & In-Mold Labeling", "primary_hub": "Annaram Hyderabad / Satara"},
    {"name": "Pennar Industries Limited", "domain": "pennarindia.com", "sector": "Cold Rolled Steel, Precision Tubes & Pre-Engineered Buildings", "primary_hub": "Patancheru / Isnapur / Chennai"},
    {"name": "Manaksia Limited", "domain": "manaksia.com", "sector": "Aluminium Rolled Products & Packaging Closures", "primary_hub": "Haldia / Bankura / Kutch"},
    {"name": "Khaitan Chemicals & Fertilizers Limited", "domain": "khaitanchemfert.com", "sector": "Single Super Phosphate & Sulphuric Acid", "primary_hub": "Nimrani Khargone / Jhansi / Dahej"},
    {"name": "Tata Coffee Limited", "domain": "tatacoffee.com", "sector": "Spray Dried & Freeze Dried Instant Coffee Processing", "primary_hub": "Theni / Toopran Medak"},
    {"name": "Orient Paper and Industries Limited", "domain": "orientpaperindia.com", "sector": "Pulp, Paper & Tissue Manufacturing", "primary_hub": "Amlai Shahdol"},
]

# Filter strictly against used set
filtered = []
for c in CANDIDATE_POOL:
    norm = c["name"].lower().strip()
    if norm not in used and not any(u == norm for u in used):
        filtered.append(c)

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

out_file = os.path.join(os.path.dirname(__file__), "prepare_batch4_company_list.py")
code_content = f'''"""Curated Batch 4 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3)."""
from typing import Dict, List

BATCH_4_COMPANIES: List[Dict[str, str]] = {json.dumps(filtered, indent=4)}

if __name__ == "__main__":
    print(f"Total Batch 4 Companies Prepared: {{len(BATCH_4_COMPANIES)}}")
'''

with open(out_file, "w", encoding="utf-8") as f:
    f.write(code_content)

print(f"Wrote {len(filtered)} companies to {out_file}")
