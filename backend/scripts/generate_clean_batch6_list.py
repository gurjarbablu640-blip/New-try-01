import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load all used companies across all previous batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES
from scripts.prepare_batch4_company_list import BATCH_4_COMPANIES
from scripts.prepare_batch5_company_list import BATCH_5_COMPANIES

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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            used.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            used.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Used: {len(used)}")

# 2. Candidate Pool for Batch 6 (Telecom Equipment, Pipes/Pumps, Specialty Metals, Auto Ancillaries, Precision Chemicals)
CANDIDATE_POOL = [
    # Telecom, Network Hardware & Optical Fiber
    {"name": "HFCL Limited", "domain": "hfcl.com", "sector": "Optical Fiber Cables & Telecom Transmission Equipment", "primary_hub": "Goa / Hyderabad / Chennai / Hosur"},
    {"name": "Tejas Networks Limited", "domain": "tejasnetworks.com", "sector": "Optical & Wireless Networking Hardware", "primary_hub": "Bengaluru / Mysuru"},
    {"name": "ITI Limited", "domain": "itiltd.in", "sector": "Telecom Defense Equipment & Smart Energy Meters", "primary_hub": "Bengaluru / Mankapur / Naini / Palakkad / Rae Bareli"},
    {"name": "Optiemus Infracom Limited", "domain": "optiemus.com", "sector": "Mobile Devices, IT Hardware & Drone Electronics", "primary_hub": "Noida Sector 63"},
    {"name": "Avantel Limited", "domain": "avantel.co.in", "sector": "Satellite Communications & Radar Systems", "primary_hub": "Visakhapatnam / Hyderabad"},
    {"name": "Nelco Limited", "domain": "nelco.co.in", "sector": "VSAT Satellite Communications & Integrated Security", "primary_hub": "Navi Mumbai Mahape"},

    # Infrastructure Pipes, Drainage & Water Transmission
    {"name": "Prince Pipes and Fittings Limited", "domain": "princepipes.com", "sector": "CPVC, UPVC & HDPE Piping Systems", "primary_hub": "Athal Silvassa / Haridwar / Chennai / Kolhapur"},
    {"name": "Skipper Limited", "domain": "skipperlimited.com", "sector": "Power Transmission Towers & Polymer Pipes", "primary_hub": "Howrah Uluberia / Batinagore"},
    {"name": "Electrosteel Castings Limited", "domain": "electrosteel.com", "sector": "Ductile Iron Pipes & Fittings", "primary_hub": "Khardah / Haldia / Elavur"},
    {"name": "Tata Metaliks Limited", "domain": "tatametaliks.com", "sector": "Ductile Iron Pipes & Foundry Grade Pig Iron", "primary_hub": "Kharagpur Paschim Medinipur"},
    {"name": "Jai Balaji Industries Limited", "domain": "jaibalajigroup.com", "sector": "Ductile Iron Pipes, Sponge Iron & TMT Bars", "primary_hub": "Durgapur / Raniganj"},

    # Specialty Metallurgy, Ferro Alloys & Sponge Iron
    {"name": "Prakash Industries Limited", "domain": "prakash.com", "sector": "Integrated Steel, Wire Rods & Ferro Alloys", "primary_hub": "Champa Janjgir / Raipur"},
    {"name": "Sarda Energy & Minerals Limited", "domain": "seml.co.in", "sector": "Ferro Alloys, Sponge Iron & Billet Rolling", "primary_hub": "Siltara Raipur"},
    {"name": "Godawari Power and Ispat Limited", "domain": "gpilindia.com", "sector": "Iron Ore Pellets, Sponge Iron & HB Wires", "primary_hub": "Siltara Raipur"},
    {"name": "Gallantt Ispat Limited", "domain": "gallantt.com", "sector": "Iron & Steel Manufacturing, TMT Bars", "primary_hub": "Gorakhpur / Kutch"},
    {"name": "Beekay Steel Industries Limited", "domain": "beekaysteel.com", "sector": "Hot Rolled Steel Sections & Bright Bars", "primary_hub": "Jamshedpur / Visakhapatnam / Chennai"},

    # Precision Chemical Additives, Pigments & Dyes
    {"name": "Bodal Chemicals Limited", "domain": "bodal.com", "sector": "Dyestuffs, Dye Intermediates & Basic Chemicals", "primary_hub": "Vatva Ahmedabad / Panoli / Roha"},
    {"name": "Kiri Industries Limited", "domain": "kiriindustries.com", "sector": "Reactive Dyes & Specialty Intermediates", "primary_hub": "Vadodara Padra"},
    {"name": "Asahi Songwon Colors Limited", "domain": "asahisongwon.com", "sector": "Phthalocyanine Pigments & Organic Dyes", "primary_hub": "Padra Vadodara / Dahej"},
    {"name": "Bhageria Industries Limited", "domain": "bhageriagroup.com", "sector": "H-Acid, Dye Intermediates & Solar Power", "primary_hub": "Vapi Valsad / Tarapur"},
    {"name": "Dynemic Products Limited", "domain": "dynemic.com", "sector": "Food Colors, Lake Colors & Dye Intermediates", "primary_hub": "Ankleshwar / Dahej"},
    {"name": "Vidhi Specialty Food Ingredients Limited", "domain": "vidhifood pageant.com", "sector": "Synthetic Food Colors & Specialty Inks", "primary_hub": "Rohi Raigad"},

    # Auto Ancillaries — Precision Sheet Metal, Casting & Seating
    {"name": "Sharda Motor Industries Limited", "domain": "shardamotor.com", "sector": "Automotive Exhaust Systems & Seating Structures", "primary_hub": "Greater Noida / Chennai / Pune / Sanand"},
    {"name": "Jay Bharat Maruti Limited", "domain": "jbmgroup.com", "sector": "Sheet Metal Stampings, Welded Assemblies & Fuel Neck", "primary_hub": "Gurugram / Manesar / Bawal / Gujarat"},
    {"name": "Harita Seating Systems Limited", "domain": "haritaseating.com", "sector": "Automotive Seating & Commercial Vehicle Seats", "primary_hub": "Hosur / Ranjangaon / Dharuhera"},
    {"name": "Autoline Industries Limited", "domain": "autolineind.com", "sector": "Sheet Metal Auto Components & Sub-Assemblies", "primary_hub": "Chakan Pune / Dharwad / Pantnagar"},
    {"name": "Rico Auto Industries Limited", "domain": "ricoauto.in", "sector": "High Pressure Aluminium & Ferrous Die Castings", "primary_hub": "Dharuhera / Gurugram / Bawal / Haridwar / Chennai"},
    {"name": "Munjal Auto Industries Limited", "domain": "munjalauto.com", "sector": "Exhaust Systems, Steel Wheel Rims & Sheet Metal", "primary_hub": "Waghodia Vadodara / Bawal / Haridwar / Dharuhera"},
    {"name": "Alicon Castalloy Limited", "domain": "alicongroup.co.in", "sector": "Aluminium Die Cast Auto Components", "primary_hub": "Shikrapur Pune / Binola"},
    {"name": "Lumax Auto Technologies Limited (Chakan Lighting)", "domain": "lumaxworld.in", "sector": "Automotive Telematics & Lighting Systems", "primary_hub": "Chakan / Pune"},
    {"name": "Sandhar Technologies Limited", "domain": "sandhargroup.com", "sector": "Automotive Locking Systems, Sheet Metal & Die Castings", "primary_hub": "Dharuhera / Manesar / Bawal / Haridwar / Attibele"},
    {"name": "PPAP Automotive Limited", "domain": "ppapco.in", "sector": "Automotive Sealing Systems & Injection Molded Parts", "primary_hub": "Noida / Greater Noida / Chennai / Pathredi"},
    {"name": "Omax Autos Limited", "domain": "omaxauto.com", "sector": "Sheet Metal Components & Machined Assemblies", "primary_hub": "Dharuhera / Gurugram / Bawal / Pantnagar / Bengaluru"},
    {"name": "Jay Ushin Limited", "domain": "jpmgroup.co.in", "sector": "Automotive Security Systems & Body Hardware", "primary_hub": "Gurugram / Manesar / Chennai / Pune"},

    # Industrial Fasteners, Springs & Cold Forming
    {"name": "Jamna Auto Industries Limited (Malur Unit)", "domain": "jaispring.com", "sector": "Parabolic Springs & Air Suspension Systems", "primary_hub": "Malur Kolar / Yamuna Nagar"},
    {"name": "GKW Limited", "domain": "gkwltd.com", "sector": "Electrical Stampings, Fasteners & Cold Formed Parts", "primary_hub": "Kolkata / Pune"},
    {"name": "Balu Forge Industries Limited", "domain": "baluindustries.com", "sector": "Precision Machined Crankshafts & Heavy Forgings", "primary_hub": "Belgaum Karnataka"},
    {"name": "Steel Strips Wheels Limited", "domain": "sswlindia.com", "sector": "Steel & Alloy Wheel Rims for Passenger & Commercial Vehicles", "primary_hub": "Dappar / Jamshedpur / Chennai / Mehsana"},
    {"name": "Rane (Madras) Limited", "domain": "ranegroup.com", "sector": "Steering & Suspension Linkages, High Precision Die Casting", "primary_hub": "Varanavasi Kanchipuram / Mysuru / Puducherry / Pantnagar"},
    {"name": "Rane Brake Lining Limited", "domain": "ranegroup.com", "sector": "Friction Materials, Brake Pads & Brake Linings", "primary_hub": "Chennai / Trichy / Hyderabad / Puducherry"},
    {"name": "Rane Engine Valve Limited", "domain": "ranegroup.com", "sector": "Engine Valves, Valve Guides & Mechanical Tappets", "primary_hub": "Alandur Chennai / Viralimalai / Hyderabad"},

    # Heavy Electricals, Motors & Generators
    {"name": "Kirloskar Electric Company Limited", "domain": "kirloskarelectric.com", "sector": "AC Motors, DC Motors, Transformers & Switchgear", "primary_hub": "Bengaluru / Hubballi / Govenahalli"},
    {"name": "Bharat Bijlee Limited", "domain": "bharatbijlee.com", "sector": "Power Transformers, Industrial Motors & Drives", "primary_hub": "Airoli Navi Mumbai"},
    {"name": "Jyoti Limited", "domain": "jyoti.com", "sector": "Turbines, Large Hydraulic Pumps & High Voltage Switchgears", "primary_hub": "Vadodara Mogar"},
    {"name": "Shilchar Technologies Limited", "domain": "shilchargroup.com", "sector": "Renewable Power Transformers & Telecom Transformers", "primary_hub": "GIDC Bil Vadodara"},
    {"name": "Universal Cables Limited", "domain": "unistar.co.in", "sector": "High Voltage XLPE Power Cables & Capacitors", "primary_hub": "Satna Madhya Pradesh"},
    {"name": "Vindhya Telelinks Limited", "domain": "vtlrewa.com", "sector": "Optical Fiber Cables & Telecommunication Infrastructure", "primary_hub": "Rewa Madhya Pradesh"},
    {"name": "Birla Cable Limited", "domain": "birlacable.com", "sector": "Telecommunication Cables & Specialized Wires", "primary_hub": "Rewa Madhya Pradesh"},

    # Specialty Packaging & Steel Drums
    {"name": "Balmer Lawrie & Co Limited", "domain": "balmerlawrie.com", "sector": "Industrial Packaging, Steel Barrels & Greases", "primary_hub": "Taloja / Manali Chennai / Silvassa / Kolkata"},
    {"name": "Everest Kanto Cylinder Limited", "domain": "everestkanto.com", "sector": "High Pressure Seamless CNG & Industrial Gas Cylinders", "primary_hub": "Tarapur / Kandla Gandhidham"},

    # Precision Auto Components & Powertrain Systems
    {"name": "Wheels India Limited", "domain": "wheelsindia.com", "sector": "Steel Wheels & Air Suspension Systems", "primary_hub": "Padi Chennai / Sriperumbudur / Rampur"},
    {"name": "Sundaram Clayton Limited", "domain": "sundaram-clayton.com", "sector": "Aluminium Die Castings & Machined Powertrain Parts", "primary_hub": "Padi Chennai / Oragadam"},
    {"name": "Brakes India Private Limited", "domain": "brakesindia.com", "sector": "Braking Systems & Ferrous Permanent Mold Castings", "primary_hub": "Padi Chennai / Sholinghur / Jhagadia"},
    {"name": "Lucas-TVS Limited", "domain": "lucas-tvs.com", "sector": "Auto Electricals, Starter Motors & Alternators", "primary_hub": "Padi Chennai / Pondicherry / Pantnagar"},
    {"name": "India Nippon Electricals Limited", "domain": "indianippon.com", "sector": "Electronic Ignition Systems & Regulators", "primary_hub": "Hosur / Pondicherry / Rewari"},
    {"name": "ZF Commercial Vehicle Control Systems India Limited", "domain": "zf.com", "sector": "Air Brake Systems, Electronic Braking & Actuators", "primary_hub": "Ambattur Chennai / Jamshedpur / Pantnagar"},
    {"name": "Tube Investments of India Limited", "domain": "tiindia.com", "sector": "Precision Cold Drawn Welded Steel Tubes & Roll Formed Sections", "primary_hub": "Avadi Chennai / Shirwal Pune / Mohali"},
    {"name": "Munjal Showa Limited", "domain": "munjalshowa.net", "sector": "Automotive Shock Absorbers & Front Forks", "primary_hub": "Manesar Gurugram / Haridwar"},
    {"name": "Rane Holdings Limited", "domain": "ranegroup.com", "sector": "Automotive Steering & Chassis Systems", "primary_hub": "Velachery Chennai"},
    {"name": "Setco Automotive Limited", "domain": "setcoauto.com", "sector": "Medium & Heavy Commercial Vehicle Clutches", "primary_hub": "Kalol Panchmahal / Sitarganj"},
    {"name": "Federal-Mogul Anand Sealings India Private Limited", "domain": "anandgroupindia.com", "sector": "Engine Gaskets & Heat Shields", "primary_hub": "Parwanoo Solan"},
    {"name": "Talbros Marugo Rubber Private Limited", "domain": "talbros.com", "sector": "Anti-Vibration Rubber Mounts & Hoses", "primary_hub": "Bawal Rewari"},
    {"name": "CIE Automotive India Limited", "domain": "cie-india.com", "sector": "Forgings, Stampings, Castings & Gears", "primary_hub": "Chakan / Pantnagar / Zaheerabad"},
    {"name": "GNA Axles Limited", "domain": "gnagroup.com", "sector": "Rear Axle Shafts & Spindles for Commercial Vehicles", "primary_hub": "Mehtiana Hoshiarpur"},
    {"name": "Sterling Biotech Limited", "domain": "sterlingbiotech.in", "sector": "Pharmaceutical Gelatin & Dicalcium Phosphate", "primary_hub": "Karakhadi Vadodara"},
]

# Filter strictly against used set
filtered = []
for c in CANDIDATE_POOL:
    norm = c["name"].lower().strip()
    if norm not in used and not any(u == norm for u in used) and "jamna auto" not in norm and "lumax auto" not in norm:
        filtered.append(c)

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

out_file = os.path.join(os.path.dirname(__file__), "prepare_batch6_company_list.py")
code_content = f'''"""Curated Batch 6 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5)."""
from typing import Dict, List

BATCH_6_COMPANIES: List[Dict[str, str]] = {json.dumps(filtered, indent=4)}

if __name__ == "__main__":
    print(f"Total Batch 6 Companies Prepared: {{len(BATCH_6_COMPANIES)}}")
'''

with open(out_file, "w", encoding="utf-8") as f:
    f.write(code_content)

print(f"Wrote {len(filtered)} companies to {out_file}")
