"""Curates Batch 9 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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
    # Defense, Aerospace & Avionics
    {"name": "Paras Defence and Space Technologies Limited", "domain": "parasdefence.com", "sector": "Defense Optics & EMP Protection Systems", "primary_hub": "Navi Mumbai Mahape"},
    {"name": "Zen Technologies Limited", "domain": "zentechnologies.com", "sector": "Combat Training Simulators & Anti-Drone Systems", "primary_hub": "Hyderabad Maheswaram"},
    {"name": "Astra Microwave Products Limited", "domain": "astramwp.com", "sector": "Radar Electronics & Satellite Payloads", "primary_hub": "Hyderabad Hardware Park"},
    {"name": "Data Patterns (India) Limited", "domain": "datapatternsindia.com", "sector": "Defense Electronics, Radars & EW Systems", "primary_hub": "Chennai Siruseri"},
    {"name": "Ideaforge Technology Limited", "domain": "ideaforgetech.com", "sector": "Unmanned Aerial Vehicles & Industrial Drones", "primary_hub": "Navi Mumbai Mahape"},

    # Precision Bearings & Heavy Tooling
    {"name": "Rolex Rings Limited", "domain": "rolexrings.com", "sector": "Forged & Machined Bearing Rings & Automotive Components", "primary_hub": "Rajkot Gondal Road"},
    {"name": "Harsha Engineers International Limited", "domain": "harshaengineers.com", "sector": "Precision Bearing Cages & Specialized Bushings", "primary_hub": "Ahmedabad Changodar"},
    {"name": "Jyoti CNC Automation Limited", "domain": "jyoti.co.in", "sector": "5-Axis Machining Centers & Precision CNC Lathes", "primary_hub": "Rajkot Metoda"},
    {"name": "Kirloskar Pneumatic Company Limited", "domain": "kirloskarpneumatic.com", "sector": "Centrifugal Air Compressors & Process Gas Packages", "primary_hub": "Pune Hadapsar / Saswad"},
    {"name": "Ingersoll-Rand (India) Limited", "domain": "ingersollrand.com", "sector": "Industrial Air Compressors & Air Treatment Systems", "primary_hub": "Ahmedabad Naroda"},

    # Automotive Systems & Components
    {"name": "JTEKT India Limited", "domain": "jtekt.co.in", "sector": "Electric Power Steering Systems & Driveline Bearings", "primary_hub": "Gurugram / Bawal"},
    {"name": "Motherson Sumi Wiring India Limited", "domain": "mswil.motherson.com", "sector": "Automotive Wiring Harnesses & Connectors", "primary_hub": "Noida / Sanand"},
    {"name": "Bharat Seats Limited", "domain": "bharatseats.net", "sector": "Automotive Seating Systems & Exhaust Components", "primary_hub": "Gurugram Sector 37"},
    {"name": "Jay Ushin Limited", "domain": "jayswitch.com", "sector": "Automotive Locks, Key Sets & Door Handles", "primary_hub": "Gurugram / Bawal"},
    {"name": "Ucal Fuel Systems Limited", "domain": "ucalfuel.com", "sector": "Throttle Bodies, Fuel Injection & Vacuum Pumps", "primary_hub": "Maraimalai Nagar Tamil Nadu"},

    # Industrial Minerals & Mining Equipment
    {"name": "Gujarat Mineral Development Corporation Limited", "domain": "gmdcltd.com", "sector": "Lignite Mining & Mineral Beneficiation Plants", "primary_hub": "Bhavnagar / Kutch"},
    {"name": "Ashapura Minechem Limited", "domain": "ashapura.com", "sector": "Bentonite & Bleaching Clay Processing", "primary_hub": "Bhuj Kutch Gujarat"},
    {"name": "20 Microns Limited", "domain": "20microns.com", "sector": "Micronized Minerals, Calcium Carbonate & Functional Fillers", "primary_hub": "Vadodara Waghodia"},

    # Electrical Equipment & Consumer Goods
    {"name": "V-Guard Industries Limited", "domain": "vguard.in", "sector": "Voltage Stabilizers, Inverters & Pumps", "primary_hub": "Kochi / Coimbatore"},
    {"name": "Bajaj Electricals Limited", "domain": "bajajelectricals.com", "sector": "Transmission Towers, High Masts & Industrial Fans", "primary_hub": "Chakan Pune / Ranjangaon"},
    {"name": "Orient Electric Limited", "domain": "orientelectric.com", "sector": "Smart Switchgear, BLDC Motors & Lighting", "primary_hub": "Faridabad / Noida"},
    {"name": "Butterfly Gandhimathi Appliances Limited", "domain": "butterflyindia.com", "sector": "LPG Stoves, Tabletop Wet Grinders & Pressure Cookers", "primary_hub": "Kelambakkam Tamil Nadu"},

    # Specialized Metals & Tubes
    {"name": "APL Apollo Tubes Limited", "domain": "aplapollo.com", "sector": "Structural Steel Tubes & Hollow Sections", "primary_hub": "Sikandrabad UP / Raipur"},
    {"name": "Surya Roshni Limited", "domain": "surya.co.in", "sector": "ERW Steel Pipes, Spiral Pipes & LED Luminaires", "primary_hub": "Bahadurgarh Haryana / Kashipur"},
    {"name": "JTL Industries Limited", "domain": "jtl.one", "sector": "Black & Galvanized ERW Steel Pipes", "primary_hub": "Mandi Gobindgarh / Mangaon"},
    {"name": "Hi-Tech Pipes Limited", "domain": "hitechpipes.in", "sector": "Hollow Sections, Solar Mounting Girders & Casing Pipes", "primary_hub": "Sikandrabad / Sanand"},
    {"name": "Prakash Industries Limited", "domain": "prakash.com", "sector": "Sponge Iron, Wire Rods & Heavy Structural Steel", "primary_hub": "Champa Chhattisgarh"},

    # Heavy Foundry & Automotive Castings
    {"name": "Bimetal Bearings Limited", "domain": "bimite.co.in", "sector": "Engine Bearings, Bushings & Thrust Washers", "primary_hub": "Coimbatore / Hosur"},
    {"name": "Nelcast Limited", "domain": "nelcast.com", "sector": "Ductile & Grey Iron Castings for Commercial Vehicles", "primary_hub": "Gudur Andhra Pradesh / Ponneri"},
    {"name": "The Anup Engineering Limited", "domain": "anupengg.com", "sector": "Heavy Heat Exchangers, Reactors & Pressure Vessels", "primary_hub": "Ahmedabad Odhav"},
    {"name": "Steelcast Limited", "domain": "steelcast.net", "sector": "Steel Castings for Mining & Locomotive Equipment", "primary_hub": "Bhavnagar Gujarat"},
    {"name": "Banco Products (India) Limited", "domain": "bancoindia.com", "sector": "Engine Cooling Modules, Radiators & Gaskets", "primary_hub": "Vadodara Bil"},

    # Specialized Packaging & Polymers
    {"name": "Cosmo First Limited", "domain": "cosmofirst.com", "sector": "BOPP Films, Thermal Lamination & Specialty Polymers", "primary_hub": "Waluj Aurangabad / Karjan"},
    {"name": "Jindal Poly Films Limited", "domain": "jindalpoly.com", "sector": "BOPET Films, Metalized Barrier Films & Non-Woven Fabrics", "primary_hub": "Nashik Igatpuri"},
    {"name": "Polyplex Corporation Limited", "domain": "polyplex.com", "sector": "Polyester Film Lines & Silicone Coated Substrates", "primary_hub": "Khatima Uttarakhand / Bajpur"},
    {"name": "Ester Industries Limited", "domain": "esterindustries.com", "sector": "Specialty Polymer Resins & Engineering Plastics", "primary_hub": "Khatima Uttarakhand"},
    {"name": "Garware Hi-Tech Films Limited", "domain": "garwarehitechfilms.com", "sector": "Solar Control Films & Paint Protection Films", "primary_hub": "Waluj Aurangabad"},

    # Precision Gears & Power Transmission
    {"name": "TD Power Systems Limited", "domain": "tdps.co.in", "sector": "AC Generators & Turbine Alternators", "primary_hub": "Bengaluru Dabaspet"},
    {"name": "Swelect Energy Systems Limited", "domain": "swelectes.com", "sector": "Solar PV Modules & Power Conditioning Units", "primary_hub": "Salem / Coimbatore"},
    {"name": "Insolation Energy Limited", "domain": "insolationenergy.in", "sector": "Solar PV Modules & Solar Cells", "primary_hub": "Jaipur Bagru"},

    # Industrial Precision Tubes & Pipes
    {"name": "Gandhi Special Tubes Limited", "domain": "gandhitubes.com", "sector": "Cold Drawn Seamless Steel Tubes & Hydraulic Lines", "primary_hub": "Halol Gujarat"},
    {"name": "Venus Pipes and Tubes Limited", "domain": "venuspipes.com", "sector": "Stainless Steel Seamless & Welded Pipes", "primary_hub": "Kutch Dhaneti Gujarat"},
    {"name": "Electrosteel Castings Limited", "domain": "electrosteel.com", "sector": "Ductile Iron Pipes & Fittings for Water Infrastructure", "primary_hub": "Kharkhari Bokaro / Elavur"},
    {"name": "Prince Pipes and Fittings Limited", "domain": "princepipes.com", "sector": "CPVC & UPVC Industrial Piping Systems", "primary_hub": "Haridwar / Athal Silvassa"},
    {"name": "Apollo Pipes Limited", "domain": "apollopipes.com", "sector": "High Density Polyethylene & Industrial Piping", "primary_hub": "Dadri Uttar Pradesh / Ahmedabad"},

    # Industrial Process Chemicals & Intermediates
    {"name": "Bodal Chemicals Limited", "domain": "bodal.com", "sector": "Dyestuff, Dye Intermediates & Basic Chemicals", "primary_hub": "Padra Vadodara / Dahej"},
    {"name": "Kiri Industries Limited", "domain": "kiriindustries.com", "sector": "Reactive Dyes & Specialty Intermediates", "primary_hub": "Vadodara / Ahmedabad"},
    {"name": "Chemfab Alkalis Limited", "domain": "chemfabalkalis.com", "sector": "Chlor-Alkali, Caustic Soda & Hydrogen", "primary_hub": "Puducherry Kalapet"},
    {"name": "Indo Amines Limited", "domain": "indoaminesltd.com", "sector": "Aliphatic Fatty Amines & Performance Chemicals", "primary_hub": "Baroda / Dombivli"},
    {"name": "Shree Pushkar Chemicals and Fertilisers Limited", "domain": "shreepushkar.com", "sector": "Dye Intermediates, Sulphur Acids & Animal Health", "primary_hub": "Lote Parshuram Ratnagiri"},

    # Specialized Machinery & Printing Systems
    {"name": "Manugraph India Limited", "domain": "manugraph.com", "sector": "Web Offset Printing Presses & Industrial Packaging Machines", "primary_hub": "Kolhapur Shiroli"},
    {"name": "Lakshmi Automatic Loom Works Limited", "domain": "lalw.in", "sector": "High Speed Weaving Machinery & Parts", "primary_hub": "Hosur Tamil Nadu"},

    # Sugar Refining, Distillery & Co-Gen Power Manufacturing
    {"name": "Balrampur Chini Mills Limited", "domain": "chini.com", "sector": "Sugar Refining, Ethanol Distilleries & Co-Gen Power", "primary_hub": "Balrampur / Gonda Uttar Pradesh"},
    {"name": "Triveni Engineering and Industries Limited", "domain": "trivenigroup.com", "sector": "High Power Industrial Turbines & Sugar Manufacturing", "primary_hub": "Mysuru / Muzaffarnagar"},
    {"name": "Dhampur Sugar Mills Limited", "domain": "dhampursugar.com", "sector": "Refined Sugar & Fuel-Grade Ethanol Manufacturing", "primary_hub": "Bijnor / Dhampur Uttar Pradesh"},
    {"name": "EID Parry (India) Limited", "domain": "eidparry.com", "sector": "Sugar Manufacturing, Distilleries & Nutraceuticals", "primary_hub": "Nellikuppam Tamil Nadu / Haliyal"},

    # High Volume Automated Food Processing & Mills
    {"name": "KRBL Limited", "domain": "krblrice.com", "sector": "Automated Rice Milling, Sorting & Grading Infrastructure", "primary_hub": "Dhuri Punjab / Gautam Budh Nagar"},
    {"name": "LT Foods Limited", "domain": "ltgroup.in", "sector": "Grain Processing & Automated Packing Complexes", "primary_hub": "Bahalgarh Haryana / Kamaspur"},
    {"name": "Avanti Feeds Limited", "domain": "avantifeeds.com", "sector": "Automated Shrimp Feed & Aquaculture Feeds", "primary_hub": "Kovvur West Godavari"},
    {"name": "Godrej Agrovet Limited", "domain": "godrejagrovet.com", "sector": "Animal Feed Processing & Palm Oil Extraction Mills", "primary_hub": "Khanna Punjab / Eluru"},

    # Paper, Pulp & Industrial Board Manufacturing
    {"name": "West Coast Paper Mills Limited", "domain": "westcoastpaper.com", "sector": "Pulp, Paper & Security Printing Paper", "primary_hub": "Dandeli Karnataka"},
    {"name": "Andhra Paper Limited", "domain": "andhrapaper.com", "sector": "Writing, Printing & Industrial Specialty Boards", "primary_hub": "Rajahmundry Andhra Pradesh"},
    {"name": "Seshasayee Paper and Boards Limited", "domain": "spbltd.com", "sector": "Integrated Paper & Multi-Layer Duplex Board", "primary_hub": "Erode Pallipalayam"},
    {"name": "Satia Industries Limited", "domain": "satiagroup.com", "sector": "Eco-Friendly Paper & Molded Tableware Machinery", "primary_hub": "Muktsar Punjab"},
    {"name": "Pudumjee Paper Products Limited", "domain": "pudumjee.com", "sector": "Specialty Food Grade Greaseproof Packaging Papers", "primary_hub": "Thergaon Pune"},

    # Automotive Friction, Valves & Brakes
    {"name": "Sundaram Brake Linings Limited", "domain": "tvsbrakes.com", "sector": "Asbestos-Free Automotive Brake Linings & Pads", "primary_hub": "Padi Chennai / Madurai"},
    {"name": "Rane Engine Valve Limited", "domain": "ranegroup.com", "sector": "Internal Combustion Engine Valves & Valve Guides", "primary_hub": "Alandur Chennai / Hyderabad"},
    {"name": "ZF Commercial Vehicle Control Systems India Limited", "domain": "zf.com", "sector": "Air Brake Actuation, Anti-Lock Braking Systems", "primary_hub": "Ambattur Chennai / Jamshedpur"},

    # Solar Submersible Pumps & Precision Motors
    {"name": "Shakti Pumps (India) Limited", "domain": "shaktipumps.com", "sector": "Solar Submersible Pumps & Stainless Steel Motors", "primary_hub": "Pithampur Madhya Pradesh"},
    {"name": "Texmo Pipes and Products Limited", "domain": "texmopipe.com", "sector": "CPVC, SWR & Agricultural Piping Complexes", "primary_hub": "Burhanpur Madhya Pradesh"},
    {"name": "India Nippon Electricals Limited", "domain": "indianippon.com", "sector": "Electronic Ignition Systems & Regulators", "primary_hub": "Hosur / Rewari"},
    {"name": "Menon Bearings Limited", "domain": "menonbearings.com", "sector": "Bi-Metal Bearings, Bushings & Thrust Washers", "primary_hub": "Kolhapur Gokul Shirgaon"},

    # Industrial Packaging, Steel Drums & Tinplate
    {"name": "Balmer Lawrie and Company Limited", "domain": "balmerlawrie.com", "sector": "Industrial Packaging, Steel Barrels & Greases", "primary_hub": "Manali Chennai / Kolkata"},
    {"name": "Hindustan Tin Works Limited", "domain": "hindustantin.biz", "sector": "Lithographed Metal Cans & Printed Tin Sheets", "primary_hub": "Muradnagar Ghaziabad"},

    # Vitrified Ceramics, Industrial Refractory Tiles & Building Infrastructure
    {"name": "Kajaria Ceramics Limited", "domain": "kajariaceramics.com", "sector": "Glazed Vitrified Tiles & Ceramic Wall Tiles", "primary_hub": "Gailpur Alwar / Morbi"},
    {"name": "Somany Ceramics Limited", "domain": "somanyceramics.com", "sector": "Polished Vitrified Tiles & Sanitaryware", "primary_hub": "Kadi Gujarat / Kassar Haryana"},
    {"name": "Cera Sanitaryware Limited", "domain": "cera-india.com", "sector": "Vitreous China Sanitaryware & Faucets", "primary_hub": "Kadi Mehsana Gujarat"},
    {"name": "HIL Limited", "domain": "hil.in", "sector": "Autoclaved Aerated Concrete Blocks & Fiber Cement", "primary_hub": "Hyderabad Golaneti / Kondapalli"},
    {"name": "Asian Granito India Limited", "domain": "aglasiangranito.com", "sector": "Quartz Slabs & Heavy Vitrified Tiles", "primary_hub": "Himmatnagar Gujarat"},

    # Precision Automotive Subsystems & Castings
    {"name": "Craftsman Automation Limited", "domain": "craftsmanautomation.com", "sector": "Cylinder Blocks, Camshafts & Aluminum Die Castings", "primary_hub": "Coimbatore / Pune"},
    {"name": "Sandhar Technologies Limited", "domain": "sandhargroup.com", "sector": "Locking Systems, Rear View Mirrors & Die Castings", "primary_hub": "Gurugram / Bawal"},
    {"name": "Happy Forgings Limited", "domain": "happyforgingsltd.com", "sector": "Heavy Forged Crankshafts & Transmission Differential Cases", "primary_hub": "Ludhiana Kanganwal"},
    {"name": "Automotive Axles Limited", "domain": "autoaxle.com", "sector": "Commercial Vehicle Rear Axles & S-Cam Drum Brakes", "primary_hub": "Mysuru Belavadi"},
    {"name": "Gabriel India Limited", "domain": "anandgroupindia.com", "sector": "Ride Control Products, Shock Absorbers & Front Forks", "primary_hub": "Pune Chakan / Hosur"},
    {"name": "Lumax Auto Technologies Limited", "domain": "lumaxworld.in", "sector": "Gear Shifters, Plastic Moulded Modules & Emission Systems", "primary_hub": "Pune Chakan / Manesar"},

    # Specialty Performance Chemicals
    {"name": "NOCIL Limited", "domain": "nocil.com", "sector": "Rubber Vulcanization Accelerators & Antioxidants", "primary_hub": "Navi Mumbai / Dahej"},
    {"name": "Camlin Fine Sciences Limited", "domain": "camlinfs.com", "sector": "Shelf Life Extension Antioxidants & Aroma Ingredients", "primary_hub": "Tarapur / Dahej"},
    {"name": "Transpek Industry Limited", "domain": "transpek.com", "sector": "Acid Chlorides & Specialty Intermediates", "primary_hub": "Atladra Vadodara"},
    {"name": "Jayant Agro-Organics Limited", "domain": "jayantagro.com", "sector": "Castor Oil Derivatives & Bio-Polyols", "primary_hub": "Palanpur Gujarat"},

    # Electrical Contacts & Switchgear Materials
    {"name": "Modison Limited", "domain": "modison.com", "sector": "Electrical Contacts, Silver Alloys & Switchgear Materials", "primary_hub": "Vapi Gujarat"},

    # Advanced Modified Polymers & Synthetic Rubbers
    {"name": "Styrenix Performance Materials Limited", "domain": "styrenix.com", "sector": "ABS Resins & Polystyrene Compounds", "primary_hub": "Nandesari Vadodara / Katol"},
    {"name": "Supreme Petrochem Limited", "domain": "supremepetrochem.com", "sector": "Expandable Polystyrene & Extruded Polystyrene Foam", "primary_hub": "Nagothane Raigad / Manali"},
    {"name": "Kingfa Science and Technology (India) Limited", "domain": "kingfaindia.com", "sector": "Modified Polypropylene & Engineering Plastics", "primary_hub": "Puducherry / Chakan Pune"},
    {"name": "Apcotex Industries Limited", "domain": "apcotex.com", "sector": "Carboxylated SB Latex & Synthetic Rubber Latices", "primary_hub": "Taloja Maharashtra / Valia"},
    {"name": "Rubfila International Limited", "domain": "rubfila.com", "sector": "Heat Resistant Latex Rubber Thread", "primary_hub": "Kanjikode Palakkad Kerala"},
    {"name": "GRP Limited", "domain": "grpweb.com", "sector": "Reclaimed Rubber & Polymer Composite Compounds", "primary_hub": "Ankleshwar / Solapur"},

    # Precision Powertrain & Camshafts
    {"name": "Precision Camshafts Limited", "domain": "pclindia.in", "sector": "Chilled Cast Iron & Assembled Camshafts", "primary_hub": "Solapur Maharashtra"},
    {"name": "The Hi-Tech Gears Limited", "domain": "hitechgears.com", "sector": "Transmission Gears, Shafts & Driveline Components", "primary_hub": "Bhiwadi Rajasthan / Manesar"},

    # Industrial Laminates, Engineered Wood & Rigid Moulding
    {"name": "Safari Industries (India) Limited", "domain": "safari.in", "sector": "Polycarbonate Luggage & Vacuum Forming Machinery", "primary_hub": "Halol Gujarat"},
    {"name": "Greenlam Industries Limited", "domain": "greenlam.com", "sector": "Decorative Laminates & Engineered Wood Panels", "primary_hub": "Behror Rajasthan / Nalagarh"},
    {"name": "Century Plyboards (India) Limited", "domain": "centuryply.com", "sector": "Plywood, Commercial Veneers & Laminates", "primary_hub": "Joka Kolkata / Kandla"},
    {"name": "Stylam Industries Limited", "domain": "stylam.com", "sector": "High Pressure Decorative Laminates & Compact Panels", "primary_hub": "Panchkula Haryana"},
    {"name": "Rushil Decor Limited", "domain": "rushil.com", "sector": "MDF Boards, Pre-Laminated Particle Boards & Laminates", "primary_hub": "Chikmagalur / Gandhinagar"},
    {"name": "Greenply Industries Limited", "domain": "greenply.com", "sector": "Plywood, Structural Decorative Veneers & MDF", "primary_hub": "Tizit Nagaland / Bamanbore"},
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

batch_9 = filtered[:50]

out_code = f'"""Curated Batch 9 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4, 5, 6, 7, 8)."""\n'
out_code += "from typing import Dict, List\n\n"
out_code += "BATCH_9_COMPANIES: List[Dict[str, str]] = " + json.dumps(batch_9, indent=4) + "\n"

target_path = os.path.join(os.path.dirname(__file__), "prepare_batch9_company_list.py")
with open(target_path, "w", encoding="utf-8") as f:
    f.write(out_code)

print(f"Wrote {len(batch_9)} companies to {target_path}")
