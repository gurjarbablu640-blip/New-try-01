"""Curates Batch 11 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25, 50, 100, 3, 4, 5, 6, 7, 8, 9, 10): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Fluid Power & Automation
    {"name": "Festo India Private Limited", "domain": "festo.com", "sector": "Pneumatic Cylinders, Solenoid Valves & Electric Drives", "primary_hub": "Bengaluru Hosur Road"},
    {"name": "SMC Corporation (India) Private Limited", "domain": "smcindia.in", "sector": "Pneumatics, Actuators & Directional Control Valves", "primary_hub": "Noida Phase II / Chennai"},
    {"name": "Bosch Rexroth (India) Private Limited", "domain": "boschrexroth.co.in", "sector": "Industrial Hydraulics, Linear Motion & Gear Units", "primary_hub": "Sanand Ahmedabad"},
    {"name": "Parker Hannifin India Private Limited", "domain": "parker.com", "sector": "Hydraulic Hoses, Fittings & Process Filtration", "primary_hub": "Mahape Navi Mumbai / Chennai"},
    {"name": "Hydac (India) Private Limited", "domain": "hydac.com", "sector": "Fluid Power Filtration, Hydraulic Accumulators & Coolers", "primary_hub": "Navi Mumbai Mahape"},
    {"name": "Donaldson India Filter Systems Private Limited", "domain": "donaldson.com", "sector": "Gas Turbine Intake Filtration & Dust Collection Systems", "primary_hub": "Gurugram Haryana"},

    # Packaging Machinery & Weighing
    {"name": "Nichrome India Limited", "domain": "nichrome.com", "sector": "Vertical Form Fill Seal Packaging Machinery", "primary_hub": "Shirwal Pune"},
    {"name": "Pakona Engineers (India) Private Limited", "domain": "pakona.com", "sector": "Horizontal Form Fill Seal Pouch Packaging Machines", "primary_hub": "Vadodara Savli"},
    {"name": "Avery India Limited", "domain": "averyweigh-tronix.com", "sector": "Heavy Duty Industrial Weighbridges & Load Cells", "primary_hub": "Ballabgarh Faridabad"},

    # Metals, Fasteners & Special Steels
    {"name": "Viraj Profiles Private Limited", "domain": "viraj.com", "sector": "Stainless Steel Flanges, Fasteners & Wire Rods", "primary_hub": "Tarapur Maharashtra Boisar"},
    {"name": "Raajratna Metal Industries Limited", "domain": "raajratna.com", "sector": "Stainless Steel Fasteners, Wire & Welding Consumables", "primary_hub": "Ahmedabad Chandial"},
    {"name": "Lakshmi Precision Screws Limited", "domain": "lpsindia.com", "sector": "High Tensile Cold Forged Fasteners & Hex Bolts", "primary_hub": "Rohtak Haryana"},
    {"name": "Assomac Machines Limited", "domain": "assomac.com", "sector": "Wire Drawing Machines & Continuous Annealing Units", "primary_hub": "Ghaziabad Uttar Pradesh"},
    {"name": "Wire World India Private Limited", "domain": "wireworld.in", "sector": "Galvanized Steel Wire & High Carbon Strands", "primary_hub": "Silvassa / Daman"},

    # Electrical Switchgear & Enclosures
    {"name": "Wago Private Limited", "domain": "wago.com", "sector": "Spring Clamp Terminal Blocks & Automation Modules", "primary_hub": "Vadodara Savli"},
    {"name": "Phoenix Contact (India) Private Limited", "domain": "phoenixcontact.co.in", "sector": "Industrial Relay Modules, Terminal Blocks & Surge Protection", "primary_hub": "Prithla Palwal Haryana"},
    {"name": "Hensel Electric India Private Limited", "domain": "hensel-electric.in", "sector": "Thermoplastic Distribution Boxes & Enclosures", "primary_hub": "Chennai Gummidipoondi"},
    {"name": "Legrand (India) Private Limited", "domain": "legrand.co.in", "sector": "MCBs, DBs, Cable Trays & Industrial Busbars", "primary_hub": "Haridwar / Jalgaon"},

    # Industrial Gases
    {"name": "Inox Air Products Private Limited", "domain": "inoxairproducts.com", "sector": "Liquid Oxygen, Nitrogen & Cryogenic Air Separation Plants", "primary_hub": "Hazira / Bokaro / Hosur"},
    {"name": "Bombay Oxygen Investments Limited", "domain": "bomoxy.com", "sector": "Compressed Industrial Gases & Special Mixtures", "primary_hub": "Mulund Mumbai / Tarapur"},
    {"name": "National Oxygen Limited", "domain": "nolgroup.com", "sector": "Industrial Oxygen & Dissolved Acetylene Plants", "primary_hub": "Puducherry / Chennai"},

    # Lubricants, Adhesives & Polymers
    {"name": "Apar Chemtek Private Limited", "domain": "aparchemtek.com", "sector": "Specialty Industrial Lubricants & Transformer Oils", "primary_hub": "Rabale Navi Mumbai"},
    {"name": "Castrol India Limited", "domain": "castrol.com", "sector": "Industrial Lubricants, Metalworking Fluids & Greases", "primary_hub": "Silvassa / Patalganga"},
    {"name": "Anabond Limited", "domain": "anabond.com", "sector": "Anaerobic Adhesives, Silicone Sealants & Epoxies", "primary_hub": "Chennai Thirumudivakkam / Pondicherry"},
    {"name": "Pidilite Speciality Chemicals", "domain": "pidilite.com", "sector": "Industrial Resins, Polymer Emulsions & Pigment Pastes", "primary_hub": "Vapi Gujarat / Mahad"},
    {"name": "Henkel Adhesives Technologies India Private Limited", "domain": "henkel.in", "sector": "Surface Technologies, Industrial Adhesives & Loctite", "primary_hub": "Kurkumbh Pune"},

    # Suspension & Heavy Auto Components
    {"name": "Lamina Suspension Products Limited", "domain": "lamina.in", "sector": "Automotive Leaf Springs & Automobile Accessories", "primary_hub": "Mangaluru Baikampady"},
    {"name": "G.S. Auto International Limited", "domain": "gsgroupindia.com", "sector": "Cast iron Suspension Components & Spring Pins", "primary_hub": "Ludhiana Dhandari Kalan"},
    {"name": "Autopins (India) Limited", "domain": "autopinsindia.com", "sector": "Parabolic Springs & Heavy Truck Leaf Springs", "primary_hub": "Faridabad / Manesar"},
    {"name": "Super Auto Forge Private Limited", "domain": "superautoforge.com", "sector": "Cold Forged Automotive Transmission & Steering Parts", "primary_hub": "Chennai Thirumazhisai"},
    {"name": "Harita Fehrer Limited", "domain": "haritafehrer.com", "sector": "Polyurethane Foam Seating & Armrests", "primary_hub": "Hosur Tamil Nadu"},

    # Process Equipment, Boilers & Pollution Control
    {"name": "Cheema Boilers Limited", "domain": "cheemaboilers.com", "sector": "Industrial Steam Boilers, AFBC Boilers & Pressure Vessels", "primary_hub": "Ropar Mohali Punjab"},
    {"name": "Forbes Marshall Private Limited", "domain": "forbesmarshall.com", "sector": "Steam Engineering, Vortex Flowmeters & Control Instrumentation", "primary_hub": "Pune Chakan"},
    {"name": "Thermax Babcock & Wilcox Energy Solutions", "domain": "thermaxglobal.com", "sector": "Supercritical Utility Boilers & Heat Recovery Units", "primary_hub": "Shirwal Pune"},
    {"name": "Vishwa Protech Private Limited", "domain": "vishwaprotech.com", "sector": "Industrial Air Pollution Control Scrubbers & Bag Filters", "primary_hub": "Ahmedabad Vatva"},

    # Precision Casting, Foundries & Forgings
    {"name": "Kirloskar Ferrous Industries Limited", "domain": "kirloskarferrous.com", "sector": "Pig Iron & Grey Iron Cylinder Blocks / Heads", "primary_hub": "Koppal Karnataka / Solapur"},
    {"name": "Nelcast Limited", "domain": "nelcast.com", "sector": "Ductile Iron & Grey Iron Castings for Commercial Vehicles", "primary_hub": "Gudur Andhra Pradesh / Ponneri"},
    {"name": "Kalyani Forge Limited", "domain": "kalyaniforge.co.in", "sector": "Precision Forged Powertrain & Engine Connecting Rods", "primary_hub": "Koregaon Bhima Pune"},
    {"name": "MM Forgings Limited", "domain": "mmforgings.com", "sector": "Closed Die Steel Forgings for Commercial Vehicles", "primary_hub": "Singampunari Tamil Nadu"},
    {"name": "Simplex Castings Limited", "domain": "simplexcastings.com", "sector": "Heavy Industrial Steel Castings & Spheroidal Graphite Castings", "primary_hub": "Bhilai Chhattisgarh / Urla Raipur"},

    # Industrial Pumps & Fluid Handling
    {"name": "WPIL Limited", "domain": "wpil.co.in", "sector": "Vertical Turbine Pumps & Large Industrial Drainage Pumps", "primary_hub": "Kolkata Panihati / Ghaziabad"},
    {"name": "Shakti Pumps (India) Limited", "domain": "shaktipumps.com", "sector": "Solar Submersible Pumps & Stainless Steel Motors", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Roto Pumps Limited", "domain": "rotopumps.com", "sector": "Progressive Cavity Pumps & Heavy Duty Slurry Pumps", "primary_hub": "Greater Noida Uttar Pradesh"},
    {"name": "Kishor Pumps Private Limited", "domain": "kishorpumps.com", "sector": "Chemical Process Pumps, Submerged & Non-Clog Pumps", "primary_hub": "Pimpri Pune"},
    {"name": "Sam Turbo Industry Private Limited", "domain": "samturbo.com", "sector": "Centrifugal Slurry Pumps for Mining, Cement & Power", "primary_hub": "Coimbatore Tamil Nadu"},

    # Cutting Tools, Tooling & Superabrasives
    {"name": "Wendt (India) Limited", "domain": "wendtindia.com", "sector": "Superabrasives, Diamond Grinding Wheels & Honing Machines", "primary_hub": "Hosur Tamil Nadu"},
    {"name": "Grindwell Norton Limited", "domain": "grindwellnorton.co.in", "sector": "Bonded Abrasives, Coated Abrasives & Silicon Carbide Grains", "primary_hub": "Mora Uran Maharashtra / Bengaluru"},
    {"name": "Carborundum Universal Limited", "domain": "cumi-murugappa.com", "sector": "Industrial Ceramics, Refractories & Bonded Abrasives", "primary_hub": "Tiruvottiyur Chennai / Edappally"},
    {"name": "Kennametal India Limited", "domain": "kennametal.com", "sector": "Hard Metal Tooling, Tungsten Carbide Inserts & Milling Cutters", "primary_hub": "Tumkur Road Bengaluru"},
    {"name": "Forbes & Company Limited", "domain": "forbes.co.in", "sector": "Bradma Industrial Marking Machines & Totem Threading Taps", "primary_hub": "Waluj Aurangabad"},

    # Power Transformers & Heavy Electrical Gear
    {"name": "Voltamp Transformers Limited", "domain": "voltamptransformers.com", "sector": "Oil Filled Power Transformers & Dry Type Transformers", "primary_hub": "Vadodara Makarpura"},
    {"name": "Transformers and Rectifiers (India) Limited", "domain": "transformerindia.com", "sector": "Extra High Voltage Transformers & Arc Furnace Transformers", "primary_hub": "Changodar Ahmedabad Moraiya"},
    {"name": "Shilchar Technologies Limited", "domain": "shilchar.com", "sector": "Electronics & Telecom Transformers & Renewable Inverter Transformers", "primary_hub": "GIDC Bil Vadodara"},
    {"name": "Indo Tech Transformers Limited", "domain": "indo-tech.com", "sector": "Power & Distribution Transformers up to 230kV", "primary_hub": "Kancheepuram Tamil Nadu"},
    {"name": "Kanohar Electricals Limited", "domain": "kanohar.com", "sector": "High Voltage Power Transformers & Substation Equipment", "primary_hub": "Meerut Uttar Pradesh"},

    # Industrial Belting & Rubber Products
    {"name": "Oriental Rubber Industries Private Limited", "domain": "orientalrubber.com", "sector": "Heavy Duty Fabric Conveyor Belts & Steel Cord Belting", "primary_hub": "Pune Sanaswadi"},
    {"name": "Forech India Private Limited", "domain": "forech.com", "sector": "Conveyor Belting, Rubber Sheeting & Wear Resistant Liners", "primary_hub": "Rai Sonipat Haryana"},
    {"name": "Fenner (India) Limited", "domain": "fennerindia.com", "sector": "Power Transmission Belts, Industrial Pulleys & Oil Seals", "primary_hub": "Madurai / Sriperumbudur"},
    {"name": "Pix Transmissions Limited", "domain": "pixtrans.com", "sector": "Industrial V-Belts, Timing Belts & Hydraulic Hoses", "primary_hub": "Nagpur Hingna Industrial Area"},

    # Industrial Valves & Fluid Flow Control
    {"name": "Advance Valves Private Limited", "domain": "advancevalves.com", "sector": "Dual Plate Check Valves & Triple Eccentric Butterfly Valves", "primary_hub": "Noida / Greater Noida"},
    {"name": "Dembla Valves Limited", "domain": "dembla.com", "sector": "Industrial Control Valves, Ball Valves & Butterfly Valves", "primary_hub": "Thane Bhiwandi Maharashtra"},
    {"name": "Microfinish Valves Private Limited", "domain": "microfinishvalves.com", "sector": "Severe Service Ball Valves & Process Control Valves", "primary_hub": "Hubballi Karnataka"},

    # Heavy Gears, Mining & Heavy Machinery
    {"name": "Elecon Engineering Company Limited", "domain": "elecon.com", "sector": "Industrial Planetary Gearboxes & Material Handling Equipment", "primary_hub": "Vallabh Vidyanagar Anand Gujarat"},
    {"name": "Revathi Equipment Limited", "domain": "reltd.co.in", "sector": "Blast Hole Drilling Rigs & Heavy Rotary Drills", "primary_hub": "Coimbatore Pollachi Road"},
    {"name": "Action Construction Equipment Limited", "domain": "ace-cranes.com", "sector": "Hydraulic Mobile Pick & Carry Cranes & Forklifts", "primary_hub": "Palwal Faridabad Haryana"},

    # Industrial Minerals & Chemicals
    {"name": "Ashapura Minechem Limited", "domain": "ashapura.com", "sector": "Bentonite Processing, Bleaching Clays & Calcined Bauxite", "primary_hub": "Bhuj Kutch Gujarat"},
    {"name": "20 Microns Limited", "domain": "20microns.com", "sector": "Micronized Industrial Minerals, Calcium Carbonate & Talc", "primary_hub": "Vadodara Waghodia Gujarat"},
    {"name": "Orient Ceratech Limited", "domain": "orientceratech.com", "sector": "Fused Aluminium Oxide Abrasive Grains & Refractory Castables", "primary_hub": "Porbandar Gujarat"},

    # Food Processing, Dairy Equipment & Heat Exchangers
    {"name": "Goma Engineering Private Limited", "domain": "goma.co.in", "sector": "High Pressure Homogenizers, Dairy Processing & Pasteurizers", "primary_hub": "Thane Majiwada Maharashtra"},
    {"name": "IDMC Limited", "domain": "idmc.coop", "sector": "Automated Dairy & Beverage Processing Plants, Silos & Tanks", "primary_hub": "Anand Vithal Udyognagar Gujarat"},
    {"name": "HRS Process Systems Limited", "domain": "hrsasia.co.in", "sector": "Corrugated Tube Heat Exchangers & Aseptic Evaporation Units", "primary_hub": "Pune Wagholi Maharashtra"},

    # Specialized Technical Textiles & Industrial Fabrics
    {"name": "Fiberweb (India) Limited", "domain": "fiberwebindia.com", "sector": "Spunbond Polypropylene Nonwoven Fabrics & Geosynthetics", "primary_hub": "Daman Dabhel"},
    {"name": "Garware Technical Fibres Limited", "domain": "garwarefibres.com", "sector": "High-Tenacity Synthetic Cordage, Ropes & Industrial Yarns", "primary_hub": "Wai Satara Maharashtra"},

    # Precision Metrology, Gauging & Specialty Cables
    {"name": "Baker Gauges India Private Limited", "domain": "bakergauges.com", "sector": "Air Gauging Systems, Dial Indicators & Electronic Gauges", "primary_hub": "Pune Viman Nagar"},
    {"name": "Cords Cable Industries Limited", "domain": "cordscable.com", "sector": "Industrial Instrumentation Cables, Control Cables & Fire Survival Cables", "primary_hub": "Bhiwadi Rajasthan"},
    {"name": "Delton Cables Limited", "domain": "deltoncables.com", "sector": "Telecom, Instrumentation & Industrial Switchboard Cables", "primary_hub": "Faridabad Haryana"},
    {"name": "Paramount Communications Limited", "domain": "paramountcables.com", "sector": "Optical Fibre Cables, Railway Signaling & Power Cables", "primary_hub": "Dharuhera Rewari Haryana"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_11 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_11.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 11 Clean Companies: {len(final_batch_11)} (Skipped: {skipped})")

# Write to prepare_batch11_company_list.py
out_path = os.path.join(os.path.dirname(__file__), "prepare_batch11_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 11 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5, 6, 7, 8, 9, 10)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_11_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_11):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == len(final_batch_11) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {len(final_batch_11)} accounts.")
