"""Curates Batch 8 Indian Industrial Manufacturing Companies with guaranteed zero overlap.

Sectors:
- Power transformers & switchgear
- Solar cell/module manufacturing
- Industrial valves & fluid control
- Precision forging & castings
- Railway wagon & rolling stock components
- Industrial packaging & specialty materials
- Defense electronics & avionics
- Heavy process equipment & boilers
"""
import os
import sys
import re
import json

# Ensure backend in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Collect all previously used company names across all batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES
from scripts.prepare_batch4_company_list import BATCH_4_COMPANIES
from scripts.prepare_batch5_company_list import BATCH_5_COMPANIES
from scripts.prepare_batch6_company_list import BATCH_6_COMPANIES
from scripts.prepare_batch7_company_list import BATCH_7_COMPANIES

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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Used: {len(all_used_names)}")

# 2. Rich candidate pool for Batch 8
CANDIDATE_POOL = [
    # Refractories & High Temperature Ceramics
    {"name": "Vesuvius India Limited", "domain": "vesuvius.com", "sector": "Refractory Linings & Flow Control Ceramics", "primary_hub": "Kolkata / Visakhapatnam"},
    {"name": "IFGL Refractories Limited", "domain": "ifglref.com", "sector": "Continuous Casting Refractories & Slide Gate Plates", "primary_hub": "Kandla SEZ / Kalunga"},
    {"name": "RHI Magnesita India Limited", "domain": "rhimagnesita.com", "sector": "Basic Refractories & Magnesia Bricks", "primary_hub": "Bhiwadi / Cuttack"},
    {"name": "Morganite Crucible (India) Limited", "domain": "morganadvancedmaterials.com", "sector": "Silicon Carbide & Clay Graphite Crucibles", "primary_hub": "Aurangabad Waluj"},
    {"name": "Orient Ceratech Limited", "domain": "orientceratech.com", "sector": "Calcined Bauxite & Fused Alumina Abrasives", "primary_hub": "Porbandar Gujarat"},

    # Industrial Abrasives & Superabrasives
    {"name": "Grindwell Norton Limited", "domain": "grindwellnorton.co.in", "sector": "Bonded Abrasives, Grinding Wheels & Superabrasives", "primary_hub": "Mora Uran / Bengaluru"},
    {"name": "Carborundum Universal Limited", "domain": "cumi-murugappa.com", "sector": "Abrasives, Industrial Ceramics & Electrominerals", "primary_hub": "Hosur / Kochi"},
    {"name": "Wendt (India) Limited", "domain": "wendtindia.com", "sector": "Diamond & CBN Grinding Wheels & Honing Machines", "primary_hub": "Hosur SIPCOT"},

    # Precision Industrial Fasteners & Cold Forgings
    {"name": "Sterling Tools Limited", "domain": "sterlingtools.com", "sector": "High Tensile Automotive & Industrial Fasteners", "primary_hub": "Faridabad / Bengaluru"},
    {"name": "Sundram Fasteners Limited", "domain": "sundram.com", "sector": "High Tensile Fasteners, Cold Extruded Parts & Iron Powder", "primary_hub": "Padi Chennai / Madurai"},
    {"name": "Simmonds Marshall Limited", "domain": "simmondsmarshall.com", "sector": "Specialized Industrial Nylon Lock Nuts & Studs", "primary_hub": "Pune Kasarwadi"},

    # Material Handling & Construction Equipment
    {"name": "Action Construction Equipment Limited", "domain": "ace-cranes.com", "sector": "Hydraulic Mobile Cranes & Material Handling Towers", "primary_hub": "Faridabad Dudhola"},
    {"name": "International Combustion (India) Limited", "domain": "iclimited.com", "sector": "Heavy Vibrating Screens & Industrial Feeders", "primary_hub": "Nagpur / Kolkata"},
    {"name": "TIL Limited", "domain": "tilindia.com", "sector": "Rough Terrain Mobile Cranes & Reach Stackers", "primary_hub": "Kolkata Kamarhatty"},
    {"name": "Gujarat Apollo Industries Limited", "domain": "apollo.co.in", "sector": "Asphalt Pavers & Mobile Crushing Plants", "primary_hub": "Mehsana Ditasan"},

    # Pressure Vessels & Gas Storage Cylinders
    {"name": "Everest Kanto Cylinder Limited", "domain": "everestkanto.com", "sector": "Seamless High Pressure Gas & CNG Cylinders", "primary_hub": "Kandla SEZ / Tarapur"},
    {"name": "Confidence Petroleum India Limited", "domain": "confidencegroup.co", "sector": "LPG & High Pressure Industrial Gas Cylinders", "primary_hub": "Nagpur Butibori"},

    # Industrial Refrigeration & Specialized HVAC
    {"name": "Frick India Limited", "domain": "frickweb.com", "sector": "Industrial Ammonia Screw Compressors & Chillers", "primary_hub": "Faridabad Sector 6"},
    {"name": "Ice Make Refrigeration Limited", "domain": "icemakeindia.com", "sector": "Cold Room Storage & Commercial Ammonia Chillers", "primary_hub": "Ahmedabad Dantali"},
    {"name": "Kirloskar Chillers Private Limited", "domain": "kirloskar-chillers.com", "sector": "Centrifugal & Screw Water Chillers", "primary_hub": "Pune Saswad"},

    # Metering & Electrical Infrastructure
    {"name": "Genus Power Infrastructures Limited", "domain": "genuspower.com", "sector": "Smart Electricity Meters & Metering Systems", "primary_hub": "Jaipur Sitapura / Haridwar"},
    {"name": "Dynamic Cables Limited", "domain": "dynamiccables.co.in", "sector": "HT/LT Aerial Bunched Cables & Industrial Conductors", "primary_hub": "Jaipur Reengus"},
    {"name": "Paramount Communications Limited", "domain": "paramountcables.com", "sector": "Railway Signaling Cables & Telecom Power Cables", "primary_hub": "Khushkhera Rajasthan / Dharuhera"},

    # Precision Industrial Tools & Collets
    {"name": "Addison and Company Limited", "domain": "addison.co.in", "sector": "HSS Twist Drills, Reamers & Milling Cutters", "primary_hub": "Chennai Mount Road"},
    {"name": "Birla Precision Technologies Limited", "domain": "birlaprecision.com", "sector": "Tool Holders, Precision Collets & ATD", "primary_hub": "Aurangabad Waluj"},

    # Heavy Marine & Defense Fabrication
    {"name": "Garden Reach Shipbuilders and Engineers Limited", "domain": "grse.in", "sector": "Warships, Patrol Vessels & Portable Steel Bridges", "primary_hub": "Kolkata Kidderpore"},
    {"name": "Mishra Dhatu Nigam Limited", "domain": "midhani-india.in", "sector": "Superalloys, Titanium Alloys & Special Steels", "primary_hub": "Hyderabad Kanchanbagh"},

    # Industrial Process & Fluid Control
    {"name": "Ion Exchange (India) Limited", "domain": "ionindia.com", "sector": "Industrial Water & Wastewater Treatment Plants", "primary_hub": "Ankleshwar / Hosur"},
    {"name": "VA Tech Wabag Limited", "domain": "wabag.com", "sector": "Desalination & Advanced Industrial Water Treatment", "primary_hub": "Chennai One"},
    {"name": "Yukon India Limited", "domain": "yukenindia.com", "sector": "Hydraulic Pumps, Valves & Power Units", "primary_hub": "Bengaluru Whitefield"},
    {"name": "Microfinish Valves Private Limited", "domain": "microfinishvalves.com", "sector": "Ball Valves & Cryogenic Valves", "primary_hub": "Hubballi Gokul"},
    {"name": "Dembla Valves Limited", "domain": "dembla.com", "sector": "Control Valves & Butterfly Valves", "primary_hub": "Thane Bhiwandi"},

    # Power Transmission & Insulators
    {"name": "Indo Tech Transformers Limited", "domain": "indo-tech.com", "sector": "Distribution & Power Transformers", "primary_hub": "Kancheepuram"},
    {"name": "HPL Electric and Power Limited", "domain": "hplindia.com", "sector": "Switchgear, Metering & Modular Devices", "primary_hub": "Gurugram / Sonepat"},
    {"name": "Modern Insulators Limited", "domain": "moderninsulators.com", "sector": "High Voltage Porcelain & Composite Insulators", "primary_hub": "Abu Road Sirohi"},
    {"name": "Frontier Springs Limited", "domain": "frontiersprings.co.in", "sector": "Railway Coil Springs & Air Springs", "primary_hub": "Kanpur Rania"},

    # Specialty Packaging & Materials
    {"name": "TCPL Packaging Limited", "domain": "tcplpack.com", "sector": "Folding Cartons & Flexible Packaging", "primary_hub": "Silvassa / Haridwar"},
    {"name": "Saint-Gobain India Private Limited", "domain": "saint-gobain.co.in", "sector": "Float Glass, Abrasives & Advanced Ceramics", "primary_hub": "Sriperumbudur Tamil Nadu"},
    {"name": "Cords Cable Industries Limited", "domain": "cordscable.com", "sector": "Control & Instrumentation Industrial Cables", "primary_hub": "Alwar Bhiwadi"},

    # Electronics & Defense Manufacturing
    {"name": "Avalon Technologies Limited", "domain": "avalontec.com", "sector": "Box Build Electronics & PCB Assemblies", "primary_hub": "Chennai MEPZ"},
    {"name": "Cyient DLM Limited", "domain": "cyientdlm.com", "sector": "Aerospace & Defense Electronics Manufacturing", "primary_hub": "Mysuru / Hyderabad"},
    {"name": "Centum Electronics Limited", "domain": "centumelectronics.com", "sector": "Advanced Microelectronics & Space Modules", "primary_hub": "Bengaluru Yelahanka"},
    {"name": "DCX Systems Limited", "domain": "dcxindia.com", "sector": "Defense Cable Harnesses & System Integration", "primary_hub": "Bengaluru Aerospace Park"},
    {"name": "SPEL Semiconductor Limited", "domain": "spel.com", "sector": "IC Packaging & Semiconductor Testing", "primary_hub": "Chennai Maraimalai Nagar"},

    # Specialized Process Equipment & Glass Lined Reactors
    {"name": "GMM Pfaudler Limited", "domain": "gmmpfaudler.com", "sector": "Glass Lined Reactors & Heavy Mixing Systems", "primary_hub": "Karamsad Gujarat"},
    {"name": "HLE Glascoat Limited", "domain": "hleglascoat.com", "sector": "Agitated Nutsche Filters & Chemical Reactors", "primary_hub": "Anand Maroli"},
    {"name": "WPIL Limited", "domain": "wpil.co.in", "sector": "Vertical Turbine Pumps & Large Irrigation Pumps", "primary_hub": "Kolkata / Ghaziabad"},
    {"name": "Dynamatic Technologies Limited", "domain": "dynamatics.com", "sector": "Aerospace Flight Structures & Hydraulic Gear Pumps", "primary_hub": "Bengaluru Peenya"},

    # Industrial Battery & Energy Storage
    {"name": "HBL Power Systems Limited", "domain": "hbl.in", "sector": "Specialized Nickel-Cadmium & Defense Batteries", "primary_hub": "Hyderabad Shamirpet"},
    {"name": "High Energy Batteries (India) Limited", "domain": "highenergy.co.in", "sector": "Silver Zinc & Torpedo Propulsion Batteries", "primary_hub": "Tiruchirappalli Mathur"},

    # Precision Automotive & Industrial Transmission
    {"name": "LG Balakrishnan and Bros Limited", "domain": "lgb.co.in", "sector": "Roller Chains, Sprockets & Precision Metal Stampings", "primary_hub": "Coimbatore Karur"},
    {"name": "Talbros Automotive Components Limited", "domain": "talbros.com", "sector": "Automotive Gaskets & Heat Shields", "primary_hub": "Faridabad / Pune"},
    {"name": "Munjal Auto Industries Limited", "domain": "munjalauto.com", "sector": "Exhaust Systems, Wheel Rims & Catalytic Converters", "primary_hub": "Vadodara Waghodia"},
    {"name": "Shivam Autotech Limited", "domain": "shivamautotech.com", "sector": "Transmission Gears, Spline Shafts & Cold Forgings", "primary_hub": "Gurugram Binola"},
    {"name": "Rane Brake Lining Limited", "domain": "ranegroup.com", "sector": "Brake Pads, Brake Linings & Clutch Facings", "primary_hub": "Chennai Ambattur"},
    {"name": "Rane (Madras) Limited", "domain": "ranegroup.com", "sector": "Steering Gear Assemblies & Ball Joints", "primary_hub": "Varanasi / Chennai"},

    # Specialty Industrial Chemistry & Surfactants
    {"name": "Fine Organic Industries Limited", "domain": "fineorganics.com", "sector": "Oleochemical Additives & Specialty Polymers", "primary_hub": "Ambernath / Dombivli"},
    {"name": "Clean Science and Technology Limited", "domain": "cleanscience.co.in", "sector": "Performance Chemicals & Antioxidants", "primary_hub": "Kurkumbh Pune"},
    {"name": "Neogen Chemicals Limited", "domain": "neogenchem.com", "sector": "Specialty Bromine & Lithium Compounds", "primary_hub": "Vadodara Dahej"},
    {"name": "Rossari Biotech Limited", "domain": "rossari.com", "sector": "Specialty Enzymes & Industrial Formulations", "primary_hub": "Dahej / Silvassa"},
    {"name": "Fairchem Organics Limited", "domain": "fairchem.in", "sector": "Dimer Acid & Natural Tocopherol", "primary_hub": "Jhagadia Gujarat"},
    {"name": "Yasho Industries Limited", "domain": "yashoindustries.com", "sector": "Rubber Accelerator Chemicals & Lubricant Additives", "primary_hub": "Vapi Gujarat"},

    # Electrical Winding Wires & Precision Conductors
    {"name": "Precision Wires India Limited", "domain": "precisionwires.com", "sector": "Enamelled Copper Winding Wires & Paper Covered Strips", "primary_hub": "Silvassa Palej"},
    {"name": "Ram Ratna Wires Limited", "domain": "rrshramik.com", "sector": "Super Enamelled Copper Wires & Submersible Winding Wires", "primary_hub": "Silvassa / Waghodia"},
    {"name": "Salzer Electronics Limited", "domain": "salzergroup.net", "sector": "Cam Operated Rotary Switches & Wire Ducts", "primary_hub": "Coimbatore Samichettipalayam"},
    {"name": "Birla Cable Limited", "domain": "birlacable.com", "sector": "Optical Fiber Cables & Structured Data Cables", "primary_hub": "Rewa Madhya Pradesh"},
    {"name": "Vindhya Telelinks Limited", "domain": "vindhyatelelinks.com", "sector": "Optical Fiber Cables & Railway Quad Cables", "primary_hub": "Rewa / Udyog Vihar"},
    {"name": "Bhagyanagar India Limited", "domain": "bhagyanagarindia.com", "sector": "Copper Busbars, Foils & Commutators", "primary_hub": "Hyderabad Nacharam"},

    # Machine Tools & Industrial Machinery
    {"name": "Lokesh Machines Limited", "domain": "lokeshmachines.com", "sector": "CNC Milling Machines, Lathes & Special Purpose Machines", "primary_hub": "Hyderabad Medchal"},
    {"name": "KPT Industries Limited", "domain": "kpttools.com", "sector": "Electric Power Tools & Blowers", "primary_hub": "Shirol Kolhapur"},
    {"name": "IMP Powers Limited", "domain": "imp-powers.com", "sector": "Extra High Voltage Power Transformers", "primary_hub": "Silvassa Umergaon"},

    # Electronic Components & PCB Assemblies
    {"name": "Sahasra Electronic Solutions Limited", "domain": "sahasra.com", "sector": "EMS, Memory Chips & Multi-Layer PCBs", "primary_hub": "Noida / Bhiwadi"},
    {"name": "MIRC Electronics Limited", "domain": "onida.com", "sector": "Consumer Electronics & Air Conditioner Manufacturing", "primary_hub": "Wada Maharashtra / Roorkee"},
    {"name": "BPL Limited", "domain": "bpl.in", "sector": "Medical Electronics & Consumer Durables", "primary_hub": "Palakkad Kerala"},

    # Industrial Polymers & Specialty Pigments
    {"name": "Poddar Pigments Limited", "domain": "poddarpigmentsltd.com", "sector": "Color Masterbatches for Synthetic Fibers & Engineering Plastics", "primary_hub": "Jaipur Vishwakarma"},
    {"name": "Balkrishna Paper Mills Limited", "domain": "bpml.in", "sector": "Duplex Coated Board & Industrial Packaging Boards", "primary_hub": "Kalyan Ambivli"},

    # Heavy Engineering & Specialty Foundry
    {"name": "Steelcast Limited", "domain": "steelcast.net", "sector": "Steel Castings for Mining & Locomotive Equipment", "primary_hub": "Bhavnagar Gujarat"},
    {"name": "The Anup Engineering Limited", "domain": "anupengg.com", "sector": "Heavy Heat Exchangers, Reactors & Pressure Vessels", "primary_hub": "Ahmedabad Odhav"},
    {"name": "Nelcast Limited", "domain": "nelcast.com", "sector": "Ductile & Grey Iron Castings for Commercial Vehicles", "primary_hub": "Gudur Andhra Pradesh / Ponneri"},
    {"name": "Bimetal Bearings Limited", "domain": "bimite.co.in", "sector": "Engine Bearings, Bushings & Thrust Washers", "primary_hub": "Coimbatore / Hosur"},
    {"name": "Sharda Motor Industries Limited", "domain": "shardamotor.com", "sector": "Exhaust Systems, Suspension Systems & Seat Frames", "primary_hub": "Greater Noida / Chennai"},
    {"name": "Banco Products (India) Limited", "domain": "bancoindia.com", "sector": "Engine Cooling Modules, Radiators & Gaskets", "primary_hub": "Vadodara Bil"},

    {"name": "Goodyear India Limited", "domain": "goodyear.co.in", "sector": "Agricultural & Farm Specialty Tires", "primary_hub": "Ballabgarh Faridabad"},
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
    
    # Exact normalized match
    if cand_norm in used_normalized:
        print(f"Duplicate (normalized): '{cand_name}' matches '{used_normalized[cand_norm]}'")
        continue

    filtered.append(cand)
    used_normalized[cand_norm] = cand_name

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

# Select exactly 50
batch_8 = filtered[:50]

out_code = f'"""Curated Batch 8 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5, 6, 7)."""\n'
out_code += "from typing import Dict, List\n\n"
out_code += "BATCH_8_COMPANIES: List[Dict[str, str]] = " + json.dumps(batch_8, indent=4) + "\n"

target_path = os.path.join(os.path.dirname(__file__), "prepare_batch8_company_list.py")
with open(target_path, "w", encoding="utf-8") as f:
    f.write(out_code)

print(f"Wrote {len(batch_8)} companies to {target_path}")
