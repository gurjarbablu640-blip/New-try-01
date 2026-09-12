import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load all used companies across all previous batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES
from scripts.prepare_batch4_company_list import BATCH_4_COMPANIES
from scripts.prepare_batch5_company_list import BATCH_5_COMPANIES
from scripts.prepare_batch6_company_list import BATCH_6_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

used = set()
for c in BATCH_100_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_3_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_4_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_5_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_6_COMPANIES:
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

# 2. Candidate Pool for Batch 7 (Industrial Automation, Aerospace Avionics, Precision CNC, Industrial Valves)
CANDIDATE_POOL = [
    # Aerospace & Defense Electronics & Avionics
    {"name": "Astra Microwave Products Limited", "domain": "astramwp.com", "sector": "Radar Electronics & Defense Telemetry Systems", "primary_hub": "Hyderabad Hardware Park / Shamshabad"},
    {"name": "Paras Defence and Space Technologies Limited", "domain": "parasdefence.com", "sector": "Defense Optics, Optronics & Space Payloads", "primary_hub": "Navi Mumbai Mahape / Thane"},
    {"name": "Apollo Micro Systems Limited", "domain": "apollo-micro.com", "sector": "Avionics, Weapon Control & Torpedo Electronics", "primary_hub": "Hyderabad Hardware Park"},
    {"name": "Sika Interplant Systems Limited", "domain": "sikaglobal.com", "sector": "Aerospace Interconnects & Hydraulics", "primary_hub": "Bengaluru Bommenahalli"},
    {"name": "DCX Systems Limited", "domain": "dcxindia.com", "sector": "System Integration & Cable Harnessing for Defense", "primary_hub": "Bengaluru Aerospace SEZ"},
    {"name": "Rossell India Limited", "domain": "rossellindia.com", "sector": "Aerospace Wire Harnesses & Test Rigs", "primary_hub": "Bengaluru Devanahalli"},

    # Industrial Automation, Robotics & Drives
    {"name": "Honeywell Automation India Limited", "domain": "honeywell.com", "sector": "Process Automation & Industrial Sensors", "primary_hub": "Hadapsar Pune / Fulgaon"},
    {"name": "ABB India Limited", "domain": "abb.co.in", "sector": "Robotics, Motion Drives & Industrial Transformers", "primary_hub": "Peenya Bengaluru / Nelamangala / Maneja Vadodara"},
    {"name": "Siemens Limited", "domain": "siemens.co.in", "sector": "Industrial Drives, Factory Automation & Switchgear", "primary_hub": "Kalwa Thane / Aurangabad / Goa"},
    {"name": "Macpower CNC Machines Limited", "domain": "macpowercnc.com", "sector": "CNC Lathes, Machining Centers & Turning Centers", "primary_hub": "Metoda Rajkot"},
    {"name": "Electronica Mechatronic Systems Private Limited", "domain": "electronicaems.com", "sector": "Linear Encoders, DROs & Coordinate Measuring Machines", "primary_hub": "Saswad Pune"},

    # Heavy Industrial Valves, Flow Control & Filtration
    {"name": "L&T Valves Limited", "domain": "lntvalves.com", "sector": "Gate, Globe, Check & Ball Valves for Oil & Gas", "primary_hub": "Ennore Chennai / Coimbatore / Kanchipuram"},
    {"name": "Forbes Marshall Private Limited", "domain": "forbesmarshall.com", "sector": "Steam Engineering, Control Valves & Boilers", "primary_hub": "Chakan Pune / Kasarwadi"},
    {"name": "Kirloskar Ebara Pumps Limited", "domain": "kepl.in", "sector": "High Pressure Boiler Feed Pumps & Steam Turbines", "primary_hub": "Kirloskarvadi Sangli"},
    {"name": "Yuken India Limited", "domain": "yukenindia.com", "sector": "Hydraulic Pumps, Valves & Power Units", "primary_hub": "Malur Kolar / Bengaluru"},
    {"name": "Hawa Valves Private Limited", "domain": "hawavalves.com", "sector": "Subsea & Pipeline Valves for Heavy Process Industries", "primary_hub": "Navi Mumbai Rabale / Khopoli"},

    # Special Purpose Machinery & Industrial Tooling
    {"name": "Bharat Fritz Werner Limited", "domain": "bfwindia.com", "sector": "Milling Machines, Machining Centers & Robotics", "primary_hub": "Peenya Bengaluru / Hosur"},
    {"name": "Micromatic Machine Tools Private Limited", "domain": "acemicromatic.net", "sector": "CNC Grinding & Turning Machinery", "primary_hub": "Bengaluru Peenya"},
    {"name": "Lakshmi Machine Works Limited", "domain": "lmwglobal.com", "sector": "Textile Spinning Machinery & CNC Machine Tools", "primary_hub": "Coimbatore Periyanaickenpalayam"},
    {"name": "Kalyani Forge Limited", "domain": "kalyaniforge.com", "sector": "Precision Cold, Warm & Hot Forged Auto Parts", "primary_hub": "Koregaon Bhima Pune / Sanaswadi"},
    {"name": "Steelco Gujarat Limited", "domain": "steelcogujarat.com", "sector": "Cold Rolled Steel Coils & Galvanized Sheets", "primary_hub": "Palej Bharuch"},

    # Precision Rubber, Seals & Hoses
    {"name": "Sundaram Multi Pap Limited", "domain": "sundaram.co.in", "sector": "Industrial Paper Converting & Stationery", "primary_hub": "Palghar Maharashtra"},
    {"name": "Pix Transmissions Limited", "domain": "pixtrans.com", "sector": "Industrial Belts, Transmission Belts & Hose Assemblies", "primary_hub": "Nagpur Hingna / Bazargaon"},
    {"name": "Oriental Carbon & Chemicals Limited", "domain": "occlindia.com", "sector": "Insoluble Sulphur for Tire Rubber Curing", "primary_hub": "Dharuhera / Mundra Kutch"},
    {"name": "Ddev Plastiks Industries Limited", "domain": "ddevgroup.in", "sector": "Polymer Compounds for Power Cables & Auto", "primary_hub": "Silvassa / Daman / Asansol"},
    {"name": "Shivalik Bimetal Controls Limited", "domain": "shivalikbimetals.com", "sector": "Thermostatic Bimetals & Shunt Resistors", "primary_hub": "Chambaghat Solan Himachal Pradesh"},

    # Electro-Chemicals & Specialty Refining
    {"name": "NOCIL Limited (Plant Unit)", "domain": "nocil.com", "sector": "Rubber Antioxidants & Accelerators", "primary_hub": "Dahej / Navi Mumbai"},
    {"name": "Meghmani Organics Limited (Agro Unit)", "domain": "meghmani.com", "sector": "Crop Protection Actives & Pigments", "primary_hub": "Dahej / Panoli / GIDC Ankleshwar"},
    {"name": "Sadhana Nitro Chem Limited", "domain": "sncl.com", "sector": "Nitrobenzene Derivatives & Optical Brighteners", "primary_hub": "Roha Raigad"},
    {"name": "IG Petrochemicals Limited", "domain": "igpetro.com", "sector": "Phthalic Anhydride & Plasticizers", "primary_hub": "Taloja Raigad"},
    {"name": "Thirumalai Chemicals Limited", "domain": "thirumalaichemicals.com", "sector": "Phthalic Anhydride & Maleic Anhydride", "primary_hub": "Ranipet Tamil Nadu / Dahej"},

    # Heavy Engineering Hardware & Fabrication
    {"name": "ISGEC Heavy Engineering Limited", "domain": "isgec.com", "sector": "Industrial Boilers, Heavy Presses & Process Equipment", "primary_hub": "Yamuna Nagar / Dahej / Rattangarh"},
    {"name": "Pennar Engineered Building Systems Limited", "domain": "pennarindia.com", "sector": "Pre-Engineered Steel Buildings & Heavy Structures", "primary_hub": "Sadashivpet Sangareddy"},
    {"name": "Salasar Techno Engineering Limited", "domain": "salasartechno.com", "sector": "Telecommunication Towers, Railway Gantry & Galvanizing", "primary_hub": "Hapur Ghaziabad"},
    {"name": "Goodluck India Limited", "domain": "goodluckindia.com", "sector": "Forged Flanges, Cold Drawn Welded Tubes & Towers", "primary_hub": "Sikandrabad Bulandshahr / Kutch"},
    {"name": "Pennar Industries Limited (Tubes Division)", "domain": "pennarindia.com", "sector": "Precision Cold Drawn Seamless Tubes", "primary_hub": "Patancheru Hyderabad"},

    # High Voltage Power Equipment & Switchgear
    {"name": "CG Power and Industrial Solutions Limited", "domain": "cgpower.com", "sector": "Power Transformers, Switchgear & Electric Motors", "primary_hub": "Kanjurmarg Mumbai / Mandideep / Malanpur / Ahmednagar"},
    {"name": "Transformers and Rectifiers (India) Limited", "domain": "transformerindia.com", "sector": "Extra High Voltage Power Transformers & Arc Furnace Transformers", "primary_hub": "Changodar Ahmedabad / Moraiya"},
    {"name": "GE T&D India Limited", "domain": "ge.com", "sector": "Gas Insulated Substations & Power Circuit Breakers", "primary_hub": "Pallavaram Chennai / Hosur / Padappai / Vadodara"},

    # Electronics & Aerospace Defense Systems
    {"name": "Data Patterns (India) Limited", "domain": "datapatternsindia.com", "sector": "Defense Radars, Electronic Warfare & Avionics", "primary_hub": "Siruseri Chennai"},
    {"name": "Dynamatic Technologies Limited", "domain": "dynamatics.com", "sector": "Aerospace Flight Structures & Hydraulic Gear Pumps", "primary_hub": "Peenya Bengaluru / Coimbatore"},
    {"name": "Garden Reach Shipbuilders & Engineers Limited", "domain": "grse.in", "sector": "Naval Warships, Patrol Vessels & Marine Gearboxes", "primary_hub": "Kolkata"},
    {"name": "Cochin Shipyard Limited", "domain": "cochinshipyard.in", "sector": "Naval Defense Vessels & Offshore Platforms", "primary_hub": "Kochi Kerala"},
    {"name": "Mazagon Dock Shipbuilders Limited", "domain": "mazagondock.in", "sector": "Submarines & Heavy Missile Destroyers", "primary_hub": "Mumbai Dockyard"},

    # Rail Rolling Stock, Metro Coaches & Heavy Bogies
    {"name": "Titagarh Rail Systems Limited", "domain": "titagarh.in", "sector": "Metro Trainsets, Passenger Coaches & Heavy Wagons", "primary_hub": "Uttarpara Hooghly / Titagarh"},
    {"name": "Jupiter Wagons Limited", "domain": "jupiterwagons.com", "sector": "Freight Wagons, Cast Steel Bogies & Brake Systems", "primary_hub": "Jabalpur / Bandel / Jamshedpur"},
    {"name": "Oriental Rail Infrastructure Limited", "domain": "orientalrail.co.in", "sector": "Railway Bogies, Couplers & Specialty Foam", "primary_hub": "Aghai Thane"},

    # Stainless Steel & Specialty High Alloy Metals
    {"name": "Jindal Stainless Limited", "domain": "jindalstainless.com", "sector": "Cold Rolled Stainless Steel & Specialty Duplex Alloys", "primary_hub": "Jajpur Odisha / Hisar Haryana"},

    # High-Yield Active Pharmaceutical Ingredients & Excipients
    {"name": "Aarti Pharmalabs Limited", "domain": "aartipharmalabs.com", "sector": "APIs, Xanthine Derivatives & Custom Chemical Synthesis", "primary_hub": "Tarapur / Vapi"},
    {"name": "Supriya Lifescience Limited", "domain": "supriyalifescience.com", "sector": "Active Pharmaceutical Ingredients & Intermediates", "primary_hub": "Khed Ratnagiri"},
    {"name": "Sigachi Industries Limited", "domain": "sigachi.com", "sector": "Microcrystalline Cellulose & Excipients", "primary_hub": "Dahej / Hyderabad / Jhagadia"},
    {"name": "Marksans Pharma Limited", "domain": "marksanspharma.com", "sector": "Soft Gelatin Capsules & High-Volume Solid Orals", "primary_hub": "Verna Goa"},
    {"name": "Caplin Point Laboratories Limited", "domain": "caplinpoint.net", "sector": "Sterile Injectables & Ophthalmic Solutions", "primary_hub": "Gummidipoondi Chennai"},
    {"name": "Lincoln Pharmaceuticals Limited", "domain": "lincolnpharma.com", "sector": "Parenteral Formulations & Liquid Ampoules", "primary_hub": "Khatraj Gandhinagar"},

    # Specialized Formulations, Biotech & Agribusiness Processing
    {"name": "Fineotex Chemical Limited", "domain": "fineotex.com", "sector": "Specialty Textile Chemicals & Pre-Treatment Emulsions", "primary_hub": "Ambernath Thane / Navi Mumbai"},
    {"name": "Gufic Biosciences Limited", "domain": "gufic.com", "sector": "Lyophilized Formulations & Critical Care Injectables", "primary_hub": "Navsari Gujarat / Belgaum"},
    {"name": "Themis Medicare Limited", "domain": "themismedicare.com", "sector": "Active Pharmaceutical Ingredients & Injectables", "primary_hub": "Vapi Valsad / Hyderabad"},
    {"name": "Panacea Biotec Limited", "domain": "panaceabiotec.com", "sector": "Recombinant Vaccines & Oral Solid Formulations", "primary_hub": "Baddi / Lalru Mohali"},
    {"name": "RPG Life Sciences Limited", "domain": "rpglifesciences.com", "sector": "Immunosuppressants & Finished Dosage Formulations", "primary_hub": "Ankleshwar / Navi Mumbai"},
    {"name": "Hester Biosciences Limited", "domain": "hester.in", "sector": "Veterinary Biologicals & Animal Vaccines", "primary_hub": "Medha Kadi Mehsana"},
    {"name": "Venky's (India) Limited", "domain": "venkys.com", "sector": "Animal Healthcare, Feed Mills & Processing Plants", "primary_hub": "Khed Pune / Anand / Hyderabad"},
    {"name": "SKM Egg Products Export (India) Limited", "domain": "skmegg.com", "sector": "Pasteurized Spray-Dried Egg Powders", "primary_hub": "Cholangapalayam Erode"},
    {"name": "Vadilal Industries Limited", "domain": "vadilalgroup.com", "sector": "Automated Dairy Freezing & Food Processing", "primary_hub": "Pundhra Gandhinagar / Bareilly"},
    {"name": "Sudarshan Pharma Industries Limited", "domain": "sudarshanpharma.com", "sector": "Bulk Drugs, Speciality Chemicals & Formulations", "primary_hub": "Raigad Maharashtra"},

    # Electronics & Semiconductor Manufacturing
    {"name": "Syrma SGS Technology Limited", "domain": "syrmasgs.com", "sector": "Electronic Manufacturing Services (EMS), RFID & PCBA", "primary_hub": "Chennai MEPZ / Baddi / Manesar / Bargur"},
    {"name": "Cyient DLM Limited", "domain": "cyientdlm.com", "sector": "Electronic Manufacturing Services for Aerospace & Defense", "primary_hub": "Mysuru / Hyderabad"},
    {"name": "Centum Electronics Limited", "domain": "centumelectronics.com", "sector": "Advanced Microelectronics, Space Satellites & Defense Modules", "primary_hub": "Bengaluru Yelahanka"},
    {"name": "Avalon Technologies Limited (Unit 2)", "domain": "avalontec.com", "sector": "Precision Sheet Metal, Aerospace Wire Harnesses & PCBAs", "primary_hub": "Chennai MEPZ"},
]

# Filter strictly against used set
filtered = []
for c in CANDIDATE_POOL:
    norm = c["name"].lower().strip()
    if norm not in used and not any(u == norm for u in used) and "avalon" not in norm and "pennar" not in norm and "shilchar" not in norm and "nocil" not in norm:
        filtered.append(c)

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

out_file = os.path.join(os.path.dirname(__file__), "prepare_batch7_company_list.py")
code_content = f'''"""Curated Batch 7 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5, 6)."""
from typing import Dict, List

BATCH_7_COMPANIES: List[Dict[str, str]] = {json.dumps(filtered, indent=4)}

if __name__ == "__main__":
    print(f"Total Batch 7 Companies Prepared: {{len(BATCH_7_COMPANIES)}}")
'''

with open(out_file, "w", encoding="utf-8") as f:
    f.write(code_content)

print(f"Wrote {len(filtered)} companies to {out_file}")
