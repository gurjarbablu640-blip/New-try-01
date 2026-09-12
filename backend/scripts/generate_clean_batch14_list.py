"""Curates Batch 14 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-13): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Aerospace, Space Electronics & Defence Explosives
    {"name": "Ananth Technologies Limited", "domain": "ananthtech.com", "sector": "Satellite Integration, Launch Vehicle Avionics & Space Sensors", "primary_hub": "Bengaluru / Hyderabad"},
    {"name": "Centum Electronics Limited", "domain": "centumelectronics.com", "sector": "Mission Critical Space Systems, Defence Electronics & Radar Subsystems", "primary_hub": "Bengaluru Yelahanka"},
    {"name": "Premier Explosives Limited", "domain": "pelgel.com", "sector": "Solid Propellants, Missile Warheads & High Energy Explosives", "primary_hub": "Peddakandukur Telangana"},
    {"name": "Solar Industries India Limited", "domain": "solargroup.com", "sector": "Industrial Explosives, Warheads, Drones & Ammunition", "primary_hub": "Nagpur Chakdoh Maharashtra"},

    # Machine Tools, Special Purpose Machinery & CNC Milling
    {"name": "HMT Limited", "domain": "hmtindia.com", "sector": "Industrial Machine Tools, CNC Turning & Tractors", "primary_hub": "Pinjore Haryana / Bengaluru"},
    {"name": "Lokesh Machines Limited", "domain": "lokeshmachines.com", "sector": "Special Purpose CNC Machines & Cam Shaft Milling Machines", "primary_hub": "Medchal Hyderabad / Pune"},
    {"name": "Bharat Fritz Werner Limited", "domain": "bfwindia.com", "sector": "Machining Centers, CNC Milling & Advanced Additive Systems", "primary_hub": "Peenya Bengaluru Karnataka"},
    {"name": "PMT Machines Limited", "domain": "pmtmachines.com", "sector": "High Precision Cylindrical Grinding & Turning Lathes", "primary_hub": "Pimpri Pune / Halol Gujarat"},

    # Industrial Polymers, Extruded PVC Pipes & Molded Products
    {"name": "Nilkamal Limited", "domain": "nilkamal.com", "sector": "Material Handling Crates, Heavy Plastic Pallets & Molded Furniture", "primary_hub": "Sinnar Nashik / Silvassa / Hosur"},
    {"name": "Prince Pipes and Fittings Limited", "domain": "princepipes.com", "sector": "CPVC, UPVC Plumbing Pipes & Heavy Underground Drainage Systems", "primary_hub": "Haridwar / Chennai / Athal Silvassa"},
    {"name": "Finolex Industries Limited", "domain": "finolexpipes.com", "sector": "PVC Pipes, Agricultural Pipe Fittings & PVC Resins", "primary_hub": "Ratnagiri / Urse Pune / Masar"},
    {"name": "Responsive Industries Limited", "domain": "responsiveindustries.com", "sector": "Industrial Vinyl Flooring, Synthetic Leather & PVC Sheeting", "primary_hub": "Boisar Tarapur Maharashtra"},

    # Renewable Wind Turbines, Generators & Rotor Blades
    {"name": "Suzlon Energy Limited", "domain": "suzlon.com", "sector": "Wind Turbine Generators, Hybrid Rotor Blades & Tubular Steel Towers", "primary_hub": "Daman / Padubidri Udupi / Bhuj"},
    {"name": "Inox Wind Limited", "domain": "inoxwind.com", "sector": "Wind Turbine Generators, Advanced Nacelles & Rotor Blades", "primary_hub": "Barwani MP / Rohika Gujarat / Una HP"},
    {"name": "Orient Green Power Company Limited", "domain": "orientgreenpower.com", "sector": "Wind Energy Generation & Substation Power Plants", "primary_hub": "Chennai / Pollachi Tamil Nadu"},

    # Heavy Integrated Cement Plants, Rotary Kilns & Grinding Units
    {"name": "Shree Cement Limited", "domain": "shreecement.com", "sector": "Integrated Cement Plants, Clinker Rotary Kilns & Grinding Units", "primary_hub": "Beawar / Ras Rajasthan / Raipur"},
    {"name": "Dalmia Bharat Limited", "domain": "dalmiabharat.com", "sector": "Super Specialty Cement, Pozzolana Clinker & Slag Cements", "primary_hub": "Dalmiapuram Tamil Nadu / Rajgangpur"},
    {"name": "Birla Corporation Limited", "domain": "birlacorporation.com", "sector": "MP Birla Portland Cement, Clinker Kilns & Jute Mills", "primary_hub": "Satna / Chanderia Chittorgarh / Durgapur"},
    {"name": "JK Lakshmi Cement Limited", "domain": "jklakshmicement.com", "sector": "Portland Pozzolana Cement, Clinker & Autoclaved Aerated Concrete", "primary_hub": "Sirohi Rajasthan / Durg Chhattisgarh"},
    {"name": "The India Cements Limited", "domain": "indiacements.co.in", "sector": "Sankar Brand Portland Cement, Blended Cements & Clinker Plants", "primary_hub": "Sankarnagar Tirunelveli / Chilamkur"},

    # Automotive Systems, Advanced Die Casting & Wiring Systems
    {"name": "Craftsman Automation Limited", "domain": "craftsmanautomation.com", "sector": "Cylinder Blocks, Cylinder Heads & Industrial Powertrain Housings", "primary_hub": "Coimbatore Kurichi / Pune"},
    {"name": "Sandhar Technologies Limited", "domain": "sandhargroup.com", "sector": "Automotive Lock Sets, Vision Systems & Aluminium Alloy Die Casting", "primary_hub": "Manesar / Bawal / Pune"},
    {"name": "Minda Corporation Limited", "domain": "sparkminda.com", "sector": "Electronic Security Systems, Wiring Harnesses & Instrument Clusters", "primary_hub": "Greater Noida / Pune Chakan"},
    {"name": "Uno Minda Limited", "domain": "unominda.com", "sector": "Automotive Alloy Wheels, Switch Assemblies & Blow Molded Tanks", "primary_hub": "Bawal Haryana / Manesar / Pune"},

    # Heavy Commercial Vehicles, Bus Bodies & Sheet Metal Cabins
    {"name": "JCBL Limited", "domain": "jcbl.com", "sector": "Custom Luxury Bus Bodies, Special Purpose Defence Vehicles & Tip Trailers", "primary_hub": "Lalru Mohali Punjab"},
    {"name": "Pinnacle Industries Limited", "domain": "pinnacleindustries.com", "sector": "Commercial Vehicle Seating Systems & Sheet Metal Stamped Cabins", "primary_hub": "Pithampur Madhya Pradesh"},
    {"name": "Sutlej Motors Limited", "domain": "sutlejmotors.com", "sector": "Intercity Luxury Coach Bodies & Specialized Armored Vehicles", "primary_hub": "Jalandhar Punjab"},

    # Specialized Metals, Aluminium Rolled Products & Extrusions
    {"name": "Hindalco Industries Limited - Aluminium Division", "domain": "hindalco.com", "sector": "Aluminium Flat Rolled Products, Extrusions & Smelters", "primary_hub": "Renukoot Sonbhadra / Belagavi / Mouda"},
    {"name": "National Aluminium Company Limited (NALCO)", "domain": "nalcoindia.com", "sector": "Bauxite Mines, Alumina Refinery & Aluminium Smelters", "primary_hub": "Damanjodi Koraput / Angul Odisha"},
    {"name": "Century Extrusions Limited", "domain": "centuryextrusions.com", "sector": "Engineered Aluminium Extruded Profiles & Hardware", "primary_hub": "Kharagpur West Bengal"},
    {"name": "Maan Aluminium Limited", "domain": "maanaluminium.com", "sector": "Aluminium Extrusions, Anodized Sections & Billets", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Bhoruka Extrusions Private Limited", "domain": "bhorukaextrusions.com", "sector": "Custom Industrial Aluminium Extrusions & Powder Coated Profiles", "primary_hub": "Mysuru Metagalli Karnataka"},

    # Industrial Packaging Films, Paper Boards & Cartons
    {"name": "Polygenta Technologies Limited", "domain": "polygenta.com", "sector": "Chemical Upcycling of PET into High Tenacity Yarns", "primary_hub": "Nashik Maharashtra"},
    {"name": "Shree Rama Multi-Tech Limited", "domain": "srmtl.com", "sector": "Multi-Layer Laminated Tubes & Co-Extruded Plastic Films", "primary_hub": "Ambaliyara Mehsana Gujarat"},

    # Electrical Power Transformers, Metering & Distribution Units
    {"name": "Permanent Magnets Limited", "domain": "pmlindia.com", "sector": "Alnico Cast Magnets, Current Sensors & Magnetic Assemblies", "primary_hub": "Silvassa / Borivali Mumbai"},

    # Petrochemicals, Basic Chemicals & Surfactants
    {"name": "GHCL Limited", "domain": "ghcl.co.in", "sector": "Soda Ash, Sodium Bicarbonate & Industrial Refined Salt", "primary_hub": "Sutrapada Veraval Gujarat"},
    {"name": "Tata Chemicals Limited", "domain": "tatachemicals.com", "sector": "Soda Ash, Sodium Bicarbonate & Heavy Industrial Chemicals", "primary_hub": "Mithapur Gujarat"},
    {"name": "Nirma Limited", "domain": "nirma.co.in", "sector": "Soda Ash, Linear Alkyl Benzene & Chlor-Alkali Complexes", "primary_hub": "Mandali / Kalatalav Bhavnagar Gujarat"},
    {"name": "Galaxy Surfactants Limited", "domain": "galaxysurfactants.com", "sector": "Specialty Surfactants, Fatty Alcohol Sulfates & Betaines", "primary_hub": "Tarapur / Taloja / Jhagadia"},
    {"name": "Aarti Surfactants Limited", "domain": "aarti-surfactants.com", "sector": "Sulfonation Surfactants & Sulfosuccinates", "primary_hub": "Pithampur Madhya Pradesh"},

    # Industrial Specialty Papers & Packaging Boards
    {"name": "Pudumjee Paper Products Limited", "domain": "pudumjee.com", "sector": "Specialty Greaseproof & Translucent Industrial Packaging Papers", "primary_hub": "Thergaon Pune Maharashtra"},
    {"name": "Shree Ajit Pulp and Paper Limited", "domain": "shreeajit.com", "sector": "Multilayer Kraft Paper & High RCT Testliner Boards", "primary_hub": "Vapi Gujarat"},
    {"name": "Orient Paper & Industries Limited", "domain": "orientpaperindia.com", "sector": "Writing & Printing Papers & Caustic Soda Plants", "primary_hub": "Amlai Shahdol Madhya Pradesh"},
    {"name": "Sirpur Paper Mills Limited", "domain": "jkpaper.com", "sector": "Pulp & Specialty Fine Writing Papers", "primary_hub": "Kagaznagar Telangana"},

    # Industrial Boilers, Compressors & Turbines
    {"name": "ISGEC Heavy Engineering Limited", "domain": "isgec.com", "sector": "Heavy Industrial Boilers, Mechanical Presses & Pressure Vessels", "primary_hub": "Yamunanagar Haryana / Dahej"},
    {"name": "Triveni Turbine Limited", "domain": "triveniturbines.com", "sector": "Industrial Back-Pressure & Condensing Steam Turbines up to 100MW", "primary_hub": "Sompura Bengaluru Karnataka"},
    {"name": "Kirloskar Pneumatic Company Limited", "domain": "kirloskarpneumatic.com", "sector": "Centrifugal Gas Compressors, Marine Gearboxes & Refrigeration", "primary_hub": "Hadapsar Pune / Saswad"},

    # Stainless Steel Flat Products & Precision Alloys
    {"name": "Jindal Stainless Limited", "domain": "jindalstainless.com", "sector": "Stainless Steel Slabs, Plates, Coils & Precision Strips", "primary_hub": "Jajpur Odisha / Hisar Haryana"},
    {"name": "Kalyani Carpenter Special Steels Private Limited", "domain": "kalyanicarpenter.com", "sector": "High Speed Tool Steels & Austenitic Stainless Alloys", "primary_hub": "Mundhwa Pune Maharashtra"},

    # Heavy Commercial Vehicles, Electric Buses & Powertrains
    {"name": "Force Motors Limited", "domain": "forcemotors.com", "sector": "Commercial Vans, Utility Vehicles & Diesel Powertrains", "primary_hub": "Pithampur / Akurdi Pune"},
    {"name": "Olectra Greentech Limited", "domain": "olectra.com", "sector": "Electric Buses, Composite Polymer Insulators & EV Platforms", "primary_hub": "Hyderabad Cherlapally / Jadcherla"},
    {"name": "JBM Auto Limited", "domain": "jbmgroup.com", "sector": "Electric City Buses, Sheet Metal Stampings & Chassis Assemblies", "primary_hub": "Faridabad / Kosi / Sanand"},

    # Automotive Steering, Valves, Brakes & Electricals
    {"name": "Lucas TVS Limited", "domain": "lucas-tvs.com", "sector": "Automotive Starter Motors, Alternators & Wiper Systems", "primary_hub": "Padi Chennai / Pondicherry"},
    {"name": "India Pistons Limited", "domain": "indiapistons.com", "sector": "Automotive Pistons, Piston Rings & Cylinder Liners", "primary_hub": "Sembiam Chennai / Maraimalai Nagar"},

    # Ductile Iron Pipes, Castings & Heavy Steel
    {"name": "Electrosteel Castings Limited", "domain": "electrosteel.com", "sector": "Ductile Iron Pipes, Fittings & Microtunneling Pipes", "primary_hub": "Khardah Kolkata / Haldia West Bengal"},
    {"name": "Kalyani Cast-Tech Limited", "domain": "kalyanicasttech.com", "sector": "Cast Steel Cargo Containers, Bogies & Couplers", "primary_hub": "Rewari Haryana"},
    {"name": "Steelcast Limited", "domain": "steelcast.net", "sector": "Steel & Alloy Steel Castings for Earthmoving & Mining Machinery", "primary_hub": "Bhavnagar Gujarat"},
    {"name": "Sintex Plastics Technology Limited", "domain": "sintexplastics.com", "sector": "Prefabricated Industrial Structures, Water Storage Tanks & Composites", "primary_hub": "Kalol Gandhinagar Gujarat"},

    # Electronics Manufacturing Services (EMS), PCBA & Avionics Modules
    {"name": "Kaynes Technology India Limited", "domain": "kaynestechnology.net", "sector": "Automotive Electronics, Industrial IoT Modules & Multilayer PCBAs", "primary_hub": "Mysuru Hebbal / Manesar"},
    {"name": "Syrma SGS Technology Limited", "domain": "syrmasgs.com", "sector": "RFID Tags, Electromagnetic Coils, Power Supplies & PCB Assemblies", "primary_hub": "Chennai MEPZ / Baddi"},
    {"name": "Avalon Technologies Limited", "domain": "avalontec.com", "sector": "Aerospace Cable Harnesses, PCBAs & Sheet Metal Enclosures", "primary_hub": "Chennai MEPZ / Bengaluru"},
    {"name": "Cyient DLM Limited", "domain": "cyientdlm.com", "sector": "Aerospace Electronic Systems, Printed Circuit Boards & Cable Harnesses", "primary_hub": "Mysuru / Hyderabad"},
    {"name": "DCX Systems Limited", "domain": "dcxindia.com", "sector": "Electronic Sub-Systems, Wire Harnesses & System Integration", "primary_hub": "Bengaluru Aerospace SEZ"},

    # Sugar, Distilleries & Biofuels Complexes
    {"name": "Bannari Amman Sugars Limited", "domain": "bannari.com", "sector": "Sugar Refining, Co-Generation Power & Industrial Distilleries", "primary_hub": "Alathukombai Erode / Nanjangud"},
    {"name": "Ponni Sugars (Erode) Limited", "domain": "ponnisugars.com", "sector": "Sugar Refining, Bagasse Co-Gen Power & Bio-Manure", "primary_hub": "Cauvery RS Erode Tamil Nadu"},
    {"name": "Kothari Sugars and Chemicals Limited", "domain": "hckotharigroup.com", "sector": "White Crystal Sugar, Co-Generation Power & Industrial Alcohol", "primary_hub": "Kattur Tiruchirappalli Tamil Nadu"},
    {"name": "Rajshree Sugars & Chemicals Limited", "domain": "rajshreesugars.com", "sector": "White Crystal Sugar, Bio-Ethanol & Co-Gen Power Plants", "primary_hub": "Theni / Villupuram Tamil Nadu"},
    {"name": "Uttam Sugar Mills Limited", "domain": "uttamsugar.in", "sector": "Refined Sugar, Ethanol Distilleries & Co-Gen Power", "primary_hub": "Roorkee / Bijnor / Muzaffarnagar"},

    # High Pressure Gas Cylinders & Industrial Storage Systems
    {"name": "Everest Kanto Cylinder Limited", "domain": "everestkanto.com", "sector": "High Pressure Seamless Steel Gas Cylinders & CNG Cascades", "primary_hub": "Tarapur Maharashtra / Kandla Gujarat"},
    {"name": "Confidence Petroleum India Limited", "domain": "confidencegroup.co", "sector": "LPG Cylinder Manufacturing & Automated Bottling Plants", "primary_hub": "Nagpur / Khopoli / Hyderabad"},
    {"name": "Alphalogic Industries Limited", "domain": "alphalogicindustries.com", "sector": "Heavy Duty Industrial Storage Racking & Mezzanine Floors", "primary_hub": "Tathawade Pune Maharashtra"},

    # Industrial Fertilizers, Specialty Amines & Nitrates
    {"name": "Mangalore Chemicals & Fertilizers Limited", "domain": "mangalorechemicals.com", "sector": "Mangala Brand Urea, Phosphatic Fertilizers & Sulphuric Acid", "primary_hub": "Panambur Mangaluru Karnataka"},
    {"name": "Southern Petrochemical Industries Corporation Limited", "domain": "spic.in", "sector": "Urea Manufacturing Plants, Bio-Fertilizers & Water Solubles", "primary_hub": "Tuticorin Tamil Nadu"},
    {"name": "Madras Fertilizers Limited", "domain": "madrasfert.co.in", "sector": "Vijay Brand Urea & NPK Complex Fertilizers", "primary_hub": "Manali Chennai Tamil Nadu"},
    {"name": "Nagarjuna Fertilizers and Chemicals Limited", "domain": "nagarjunafertilizers.com", "sector": "Urea Manufacturing Plants & Micro-Irrigation Equipment", "primary_hub": "Kakinada Andhra Pradesh"},
    {"name": "Deepak Nitrite Limited", "domain": "godeepak.com", "sector": "Sodium Nitrite, Nitroaromatics, Phenol & Acetone Complexes", "primary_hub": "Nandesari Vadodara / Dahej"},
    {"name": "Alkyl Amines Chemicals Limited", "domain": "alkylamines.com", "sector": "Aliphatic Amines, Amine Derivatives & Specialty Fine Chemicals", "primary_hub": "Patalganga / Kurkumbh / Dahej"},
    {"name": "Balaji Amines Limited", "domain": "balajiamines.com", "sector": "Methylamines, Ethylamines, Specialty Chemicals & Solvents", "primary_hub": "Solapur Maharashtra"},
    {"name": "Ami Organics Limited", "domain": "amiorganics.com", "sector": "Advanced Pharmaceutical Intermediates & Fine Specialty Chemicals", "primary_hub": "Sachin Surat / Ankleshwar Gujarat"},

    # Industrial Explosives & Mining Accessories
    {"name": "GOCL Corporation Limited", "domain": "goclcorp.com", "sector": "Industrial Explosives, Mining Detonators & Special Accessories", "primary_hub": "Hyderabad Kukatpally / Rourkela Odisha"},
    {"name": "Ideal Detonators Private Limited", "domain": "idealdetonators.com", "sector": "Electric Detonators, Cord Relays & Detonating Fuses", "primary_hub": "Hyderabad Telangana"},

    # Specialty Winding Wires, Copper Strips & Non-Ferrous Alloys
    {"name": "Precision Wires India Limited", "domain": "precisionwires.com", "sector": "Enamelled Copper Winding Wires & Submersible Copper Strips", "primary_hub": "Palej Bharuch / Silvassa"},
    {"name": "Ram Ratna Wires Limited", "domain": "rrshramik.com", "sector": "Enamelled Copper Wires, Strips & Submersible Winding Wires", "primary_hub": "Silvassa / Waghodia Vadodara"},
    {"name": "Shera Energy Limited", "domain": "sheraenergy.com", "sector": "Copper Tubes, Winding Wires & Brass Rod Extrusions", "primary_hub": "Jaipur Reengus Rajasthan"},
    {"name": "Modison Limited", "domain": "modison.com", "sector": "Electrical Contact Materials, Silver Alloys & High Voltage Contacts", "primary_hub": "Vapi Gujarat"},

    # Specialty Pigments, Chlor-Alkali & Fine Chemicals
    {"name": "Kanoria Chemicals & Industries Limited", "domain": "kanoriachem.com", "sector": "Pentaerythritol, Formaldehyde & Industrial Solvents", "primary_hub": "Ankleshwar Gujarat / Renukoot"},
    {"name": "DCM Shriram Limited - Chemical Division", "domain": "dcmshriram.com", "sector": "Caustic Soda, Liquid Chlorine & PVC Compounds", "primary_hub": "Kota Rajasthan / Jhagadia Bharuch"},
    {"name": "Sudarshan Chemical Industries Limited", "domain": "sudarshan.com", "sector": "Organic, Inorganic & Pearlescent Pigments", "primary_hub": "Roha / Mahad Maharashtra"},
    {"name": "Heubach Colorants India Limited", "domain": "heubachcolor.com", "sector": "Organic Pigments, Dyes & Specialty Pigment Preparations", "primary_hub": "Roha Raigad Maharashtra"},

    # Automotive Rear Axles, Splined Shafts & Precision Springs
    {"name": "Stumpp Schuele & Somappa Springs Private Limited", "domain": "sss-springs.com", "sector": "Precision Valve Springs, Suspension Springs & Wire Forms", "primary_hub": "Bengaluru Hosur Road"},
    {"name": "Talbros Engineering Limited", "domain": "talbrosaxles.com", "sector": "Automotive Rear Axle Shafts & Heavy Spindles", "primary_hub": "Faridabad Haryana"},
    {"name": "GNA Axles Limited", "domain": "gnaaxles.com", "sector": "Rear Axle Shafts, Splined Shafts & Drive Flanges", "primary_hub": "Mehtiana Hoshiarpur Punjab"},
    {"name": "Sujan Industries", "domain": "sujanindustries.com", "sector": "Rubber-to-Metal Bonded Anti-Vibration Mounts & Bushes", "primary_hub": "Vasai Palghar Maharashtra"},

    # Heavy Integrated Sponge Iron, Pellets & Structural Steels
    {"name": "Sarda Energy & Minerals Limited", "domain": "seml.co.in", "sector": "Sponge Iron, Ferroalloys, Billets & Wire Rods", "primary_hub": "Siltara Raipur Chhattisgarh"},
    {"name": "Godawari Power and Ispat Limited", "domain": "gpilindia.com", "sector": "Iron Ore Pellets, Sponge Iron & HB Wire", "primary_hub": "Siltara Raipur Chhattisgarh"},
    {"name": "Sharda Ispat Limited", "domain": "shardaispat.com", "sector": "Rolled Steel Products, Spring Steel Flats & Special Sections", "primary_hub": "Kamptee Road Nagpur Maharashtra"},
    {"name": "Prakash Industries Limited", "domain": "prakash.com", "sector": "Integrated Steel Plant, Wire Rods & Structural Sections", "primary_hub": "Champa Janjgir Chhattisgarh"},
    {"name": "Lloyds Metals and Energy Limited", "domain": "lloyds.in", "sector": "Direct Reduced Iron, Sponge Iron & Power Plants", "primary_hub": "Ghugus Chandrapur Maharashtra"},
    {"name": "Gokaldas Exports Limited", "domain": "gokaldasexports.com", "sector": "Apparel Manufacturing Complexes & Industrial Sewing Plants", "primary_hub": "Bengaluru Peenya / Tumakuru Karnataka"},
    {"name": "Page Industries Limited", "domain": "pageind.com", "sector": "Knitted Garments, Elastic Webbing & Automated Cutting Units", "primary_hub": "Bengaluru Bommasandra / Hassan"},
    {"name": "Kitex Garments Limited", "domain": "kitexgarments.com", "sector": "Automated Infant Wear Processing & Fabric Dyeing Plants", "primary_hub": "Kizhakkambalam Kochi Kerala"},
    {"name": "Arvind Limited", "domain": "arvind.com", "sector": "Denim Fabrics, Technical Textiles & Advanced Materials", "primary_hub": "Naroda Ahmedabad / Santej Gujarat"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_14 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_14.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 14 Clean Companies: {len(final_batch_14)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch14_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 14 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-13)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_14_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_14):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == len(final_batch_14) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {len(final_batch_14)} accounts.")
