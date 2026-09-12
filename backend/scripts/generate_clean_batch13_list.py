"""Curates Batch 13 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-12): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Aerospace, Defence & Advanced Precision Systems
    {"name": "Astra Microwave Products Limited", "domain": "astramwp.com", "sector": "Radar Electronics, EW Systems & Sub-Systems", "primary_hub": "Hyderabad Hardware Park"},
    {"name": "Data Patterns (India) Limited", "domain": "datapatternsindia.com", "sector": "Radars, Avionics & Missile Guidance Electronics", "primary_hub": "Siruseri SIPCOT Chennai"},
    {"name": "Zen Technologies Limited", "domain": "zentechnologies.com", "sector": "Combat Training Simulators & Anti-Drone Systems", "primary_hub": "Maheswaram Hyderabad"},
    {"name": "Paras Defence and Space Technologies Limited", "domain": "parasdefence.com", "sector": "Defence Optics, Submarine Periscopes & EMP Protection", "primary_hub": "Navi Mumbai Nerul"},
    {"name": "Apollo Micro Systems Limited", "domain": "apollo-micro.com", "sector": "Avionics, Onboard Computers & Weapon Electronics", "primary_hub": "Hyderabad Kushaiguda"},
    {"name": "Dynamatic Technologies Limited", "domain": "dynamatics.com", "sector": "Aerospace Aerostructures & Hydraulic Gear Pumps", "primary_hub": "Bengaluru Peenya"},
    {"name": "Sika Interplant Systems Limited", "domain": "sikaglobal.com", "sector": "Aerospace Hydraulics & Landing Gear Components", "primary_hub": "Bengaluru Whitefield"},

    # Chemical Process Intermediates, Specialty Polymers & Resins
    {"name": "Fairchem Organics Limited", "domain": "fairchem.in", "sector": "Oleochemicals, Dimer Acid & Natural Vitamin E", "primary_hub": "Jhagadia Bharuch Gujarat"},
    {"name": "Fineotex Chemical Limited", "domain": "fineotex.com", "sector": "Specialty Textile Chemicals & Cleaning Polymers", "primary_hub": "Ambernath Thane / Navi Mumbai"},
    {"name": "Foseco India Limited", "domain": "vesuvius.com", "sector": "Foundry Fluxes, Refractory Coatings & Feeding Systems", "primary_hub": "Sanaswadi Pune / Puducherry"},
    {"name": "Rossari Biotech Limited", "domain": "rossari.com", "sector": "Specialty Performance Chemicals & Animal Nutrition", "primary_hub": "Dahej Gujarat / Silvassa"},
    {"name": "Clean Science and Technology Limited", "domain": "cleanscience.co.in", "sector": "MEHQ, BHA & 4-MAP Performance Chemicals", "primary_hub": "Kurkumbh Pune Maharashtra"},
    {"name": "Tatva Chintan Pharma Chem Limited", "domain": "tatvachintan.com", "sector": "Structure Directing Agents & Phase Transfer Catalysts", "primary_hub": "Dahej / Ankleshwar Gujarat"},

    # Precision Bearings & Heavy Power Transmission
    {"name": "Rolex Rings Limited", "domain": "rolexrings.com", "sector": "Hot Rolled Forged Rings & Automotive Transmission Parts", "primary_hub": "Rajkot Gondal Road Gujarat"},
    {"name": "Harsha Engineers International Limited", "domain": "harshaengineers.com", "sector": "Precision Bearing Cages & Stamped Brass Cages", "primary_hub": "Changodar Ahmedabad"},
    {"name": "NRB Bearings Limited", "domain": "nrbbearings.com", "sector": "Needle Roller Bearings & Cylindrical Roller Bearings", "primary_hub": "Thane / Jalgaon / Waluj"},
    {"name": "Menon Bearings Limited", "domain": "menonbearings.com", "sector": "Bi-Metal Engine Bearings, Bushes & Thrust Washers", "primary_hub": "Kolhapur Gokul Shirgaon"},
    {"name": "Galaxy Bearings Limited", "domain": "galaxybearings.com", "sector": "Tapered Roller Bearings & Wheel Hub Units", "primary_hub": "Rajkot Shapar Veraval"},

    # Heavy Commercial Electricals, Transformers & Switchboards
    {"name": "Jyoti Limited", "domain": "jyoti.com", "sector": "Centrifugal Pumps, Vacuum Circuit Breakers & Hydro Turbines", "primary_hub": "Vadodara Mogar Gujarat"},
    {"name": "Kirloskar Electric Company Limited", "domain": "kirloskarelectric.com", "sector": "AC/DC Industrial Motors, Generators & Transformers", "primary_hub": "Hubballi / Bengaluru"},
    {"name": "Bharat Bijlee Limited", "domain": "bharatbijlee.com", "sector": "Power Transformers, Electric Motors & Elevator Drives", "primary_hub": "Airoli Navi Mumbai"},
    {"name": "Stelmec Limited", "domain": "stelmec.com", "sector": "Medium Voltage Switchgear, Ring Main Units & Breakers", "primary_hub": "Palghar / Ahmedabad"},

    # Agrochem, Fertilizer & Special Nutrients
    {"name": "Coromandel International Limited", "domain": "coromandel.biz", "sector": "Phosphatic Fertilizers & Crop Protection Chemicals", "primary_hub": "Ennore / Kakinada / Visakhapatnam"},
    {"name": "Deepak Fertilisers and Petrochemicals Corporation Limited", "domain": "dfpcl.com", "sector": "Technical Ammonium Nitrate & Industrial Nitric Acid", "primary_hub": "Taloja / Dahej"},
    {"name": "National Fertilizers Limited", "domain": "nationalfertilizers.com", "sector": "Urea Manufacturing Plants & Industrial Chemical Units", "primary_hub": "Panipat / Vijaipur / Nangal"},
    {"name": "Rashtriya Chemicals and Fertilizers Limited", "domain": "rcfltd.com", "sector": "Urea, Complex Fertilizers & Industrial Methanol", "primary_hub": "Trombay Mumbai / Thal Raigad"},
    {"name": "Chambal Fertilisers and Chemicals Limited", "domain": "chambalfertilisers.com", "sector": "Urea Manufacturing Plants & Agro-Chemical Complexes", "primary_hub": "Gadepan Kota Rajasthan"},

    # Steel Pipes, ERW Tubes & Heavy Structural Hollow Sections
    {"name": "APL Apollo Tubes Limited", "domain": "aplapollo.com", "sector": "Structural Steel Hollow Sections & Galvanized Tubes", "primary_hub": "Sikandrabad / Raipur / Hosur"},
    {"name": "Surya Roshni Limited", "domain": "surya.co.in", "sector": "ERW Steel Pipes, Spiral Pipes & LED Lighting Plants", "primary_hub": "Bahadurgarh / Gwalior / Bhuj"},
    {"name": "Rama Steel Tubes Limited", "domain": "ramasteeltubes.com", "sector": "Structural Steel Pipes & Scaffolding Tubes", "primary_hub": "Sahibabad Ghaziabad / Khopoli"},
    {"name": "Hi-Tech Pipes Limited", "domain": "hitechpipes.in", "sector": "Steel Tubes, Hollow Sections & Cold Rolled Coils", "primary_hub": "Sikandrabad / Sanand / Hindupur"},
    {"name": "JTL Industries Limited", "domain": "jtl.one", "sector": "Galvanized Steel Pipes & Solar Mounting Structures", "primary_hub": "Derabassi Punjab / Mangaon Maharashtra"},

    # Heavy Casting, Railway Rolling Stock & Specialized Wagons
    {"name": "Titagarh Rail Systems Limited", "domain": "titagarh.in", "sector": "Passenger Rolling Stock, Freight Wagons & Metro Coaches", "primary_hub": "Titagarh / Uttarpara West Bengal"},
    {"name": "Jupiter Wagons Limited", "domain": "jupiterwagons.com", "sector": "Railway Freight Wagons, Bogies & Couplers", "primary_hub": "Jabalpur / Bandel / Kolkata"},
    {"name": "Oriental Foundry Private Limited", "domain": "orientalrail.com", "sector": "Heavy Railway Cast Steel Bogies & Couplers", "primary_hub": "Bhachau Kutch Gujarat"},

    # Automotive Batteries, Cables & Lighting
    {"name": "Fiem Industries Limited", "domain": "fiemindustries.com", "sector": "Automotive Lighting Systems & Rear View Mirrors", "primary_hub": "Rai Sonipat / Hosur"},
    {"name": "Lumax Auto Technologies Limited", "domain": "lumaxworld.in", "sector": "Automotive Shift Towers, Intake Systems & Lighting", "primary_hub": "Chakan Pune / Manesar"},
    {"name": "Rico Auto Industries Limited", "domain": "ricoauto.in", "sector": "Aluminium Die Casting & Machined Engine Powertrains", "primary_hub": "Gurugram / Dharuhera / Bawal"},
    {"name": "Omax Autos Limited", "domain": "omaxauto.com", "sector": "Sheet Metal Automotive Stampings & Welded Frames", "primary_hub": "Dharuhera Haryana / Pantnagar"},
    {"name": "Jay Bharat Maruti Limited", "domain": "jbmgroup.com", "sector": "Sheet Metal Stampings, Welded Assemblies & Exhaust Systems", "primary_hub": "Gurugram / Manesar"},

    # Industrial Furnaces, Foundry Equipment & Metallurgy
    {"name": "Inductotherm (India) Private Limited", "domain": "inductothermindia.com", "sector": "Induction Melting Furnaces, Power Supplies & Heating Systems", "primary_hub": "Sanand Ahmedabad Gujarat"},
    {"name": "Electrotherm (India) Limited", "domain": "electrotherm.com", "sector": "Steel Melting Furnaces, Sponge Iron Plants & Ductile Iron Pipes", "primary_hub": "Samakhiyali Kutch Gujarat"},
    {"name": "DISA India Limited", "domain": "disagroup.com", "sector": "Green Sand Moulding Machines & Foundry Machinery", "primary_hub": "Tumakuru Karnataka / Hosakote"},
    {"name": "Wesman Engineering Company Private Limited", "domain": "wesman.com", "sector": "Industrial Reheating Furnaces, Combustion Burners & Foundry Equipment", "primary_hub": "Kolkata / Pune"},
    {"name": "Mukand Limited", "domain": "mukand.com", "sector": "Special Alloy Steels, Stainless Steel Billets & Heavy Industrial Cranes", "primary_hub": "Kalwe Thane / Hospet Bellary"},
    {"name": "BEML Limited", "domain": "bemlindia.in", "sector": "Mining Earthmovers, Heavy Dump Trucks & Metro Coaches", "primary_hub": "Kolar Gold Fields / Mysuru / Bengaluru"},

    # Precision Gears, Power Transmission & Industrial Engines
    {"name": "Shanthi Gears Limited", "domain": "shanthigears.com", "sector": "Custom Industrial Gearboxes, Worm Reducers & Helical Geared Motors", "primary_hub": "Coimbatore Singanallur"},
    {"name": "Essential Power Transmission Private Limited", "domain": "essentialgears.com", "sector": "Heavy Duty Industrial Worm Gearboxes & Planetary Drives", "primary_hub": "Shapar Rajkot Gujarat"},
    {"name": "Greaves Cotton Limited", "domain": "greavescotton.com", "sector": "Multi-Cylinder Diesel Engines, Generator Sets & Powertrains", "primary_hub": "Ranipet Tamil Nadu / Aurangabad"},
    {"name": "Simpson & Company Limited", "domain": "simpsons.co.in", "sector": "Multi-Cylinder Industrial Diesel Engines & Tractor Engines", "primary_hub": "Huzur Gardens Chennai"},

    # Machine Tools, CNC Turning & Precision Tooling
    {"name": "Lakshmi Machine Works Limited", "domain": "lmwglobal.com", "sector": "CNC Turning Centers, Machining Centers & Textile Machinery", "primary_hub": "Coimbatore Perianaickenpalayam"},
    {"name": "Ace Designers Limited", "domain": "acemicromatic.net", "sector": "CNC Horizontal Turning Lathes & Twin Spindle Machines", "primary_hub": "Peenya Bengaluru Karnataka"},
    {"name": "Micromatic Grinding Technologies Private Limited", "domain": "micromaticgrinding.com", "sector": "High Precision External & Internal Cylindrical Grinding Machines", "primary_hub": "Ghaziabad / Bengaluru"},
    {"name": "Macpower CNC Machines Limited", "domain": "macpowercnc.com", "sector": "CNC Turning Lathes, Vertical Machining Centers & Drilling Tapping Units", "primary_hub": "Rajkot Shapar Gujarat"},
    {"name": "Godrej & Boyce Manufacturing Company Limited - Tooling Division", "domain": "godrej.com", "sector": "High Precision Sheet Metal Stamping Dies & Large Compression Moulds", "primary_hub": "Vikhroli Mumbai / Shirwal Pune"},

    # Industrial Water Treatment, Desalination & Effluent Plants
    {"name": "Ion Exchange (India) Limited", "domain": "ionindia.com", "sector": "Industrial Water Treatment Plants, Ion Exchange Resins & RO Membranes", "primary_hub": "Ankleshwar / Hosur / Wada"},
    {"name": "VA Tech Wabag Limited", "domain": "wabag.com", "sector": "Industrial Effluent Treatment Plants, Desalination & Sewage Recycling", "primary_hub": "Sunmar Chennai / Dahej"},
    {"name": "Fontus Water Private Limited", "domain": "fontuswater.com", "sector": "Zero Liquid Discharge Plants, Ultrafiltration & Effluent Treatment", "primary_hub": "New Delhi / Baddi Himachal Pradesh"},
    {"name": "Doshion Veolia Water Solutions Private Limited", "domain": "doshion.com", "sector": "Industrial Demineralization Plants & Wastewater Recycle Units", "primary_hub": "Vatva Ahmedabad Gujarat"},

    # Industrial Electricals, Switchgear & Power Distribution
    {"name": "Goyal MG Gases Private Limited", "domain": "goyalmg.com", "sector": "Industrial Liquid Oxygen, Nitrogen & Cryogenic Gas Refilling Plants", "primary_hub": "Ballari Karnataka / Ghaziabad"},
    {"name": "C&S Electric Limited", "domain": "cselectric.co.in", "sector": "Air Circuit Breakers, Molded Case Circuit Breakers & Busduct Systems", "primary_hub": "Noida / Haridwar"},
    {"name": "Schneider Electric India Private Limited", "domain": "se.com", "sector": "Medium & Low Voltage Switchgear, Automation & Distribution Transformers", "primary_hub": "Mahape Navi Mumbai / Ahmednagar"},

    # Petrochemicals, Polymers & BOPP Packaging Films
    {"name": "DCW Limited", "domain": "dcwltd.com", "sector": "Caustic Soda, PVC Resins, CPVC & Synthetic Rutile Complexes", "primary_hub": "Sahupuram Thoothukudi Tamil Nadu"},
    {"name": "Supreme Petrochem Limited", "domain": "supremepetrochem.com", "sector": "Polystyrene, Expandable Polystyrene & Extruded Polystyrene Boards", "primary_hub": "Nagothane Raigad / Manali Chennai"},
    {"name": "Cosmo First Limited", "domain": "cosmofirst.com", "sector": "BOPP Films, Speciality Barrier Films & Thermal Lamination", "primary_hub": "Waluj Aurangabad / Karjan Vadodara"},
    {"name": "Polyplex Corporation Limited", "domain": "polyplex.com", "sector": "BOPET Thin Packaging Films & Sarafil Coated Polyester Films", "primary_hub": "Khatima / Bajpur Uttarakhand"},
    {"name": "Jindal Poly Films Limited", "domain": "jindalpoly.com", "sector": "BOPET & BOPP Flexible Packaging Films", "primary_hub": "Nashik Igatpuri Maharashtra"},
    {"name": "Ester Industries Limited", "domain": "esterindustries.com", "sector": "Polyester Packaging Films & Engineering Plastic Compounds", "primary_hub": "Khatima Udham Singh Nagar"},
    {"name": "Garware Hi-Tech Films Limited", "domain": "garwarehitechfilms.com", "sector": "Suncontrol Window Films & Automotive Paint Protection Films", "primary_hub": "Waluj / Chikalthana Aurangabad"},

    # Power Transmission Towers, Substation Fabrications & Structural Steel
    {"name": "Skipper Limited", "domain": "skipperlimited.com", "sector": "Power Transmission Line Towers, Monopoles & Solar Structures", "primary_hub": "Uluberia Howrah West Bengal"},
    {"name": "KEC International Limited", "domain": "kecrpg.com", "sector": "Transmission Line Towers, Railway Electrification & EHV Cables", "primary_hub": "Butibori Nagpur / Vadodara"},
    {"name": "Kalpataru Projects International Limited", "domain": "kalpataruprojects.com", "sector": "High Voltage Transmission Towers, Substation Infrastructure & Pipelines", "primary_hub": "Gandhinagar Gujarat / Raipur"},
    {"name": "Salasar Techno Engineering Limited", "domain": "salasartechno.com", "sector": "Galvanized Telecom Towers, Solar Module Mounting Structures & Heavy Steel", "primary_hub": "Hapur Uttar Pradesh"},

    # Industrial Valves, Actuators & Steam Management
    {"name": "Rotork Controls (India) Private Limited", "domain": "rotork.com", "sector": "Heavy Duty Electric, Pneumatic & Hydraulic Valve Actuators", "primary_hub": "Chennai Ambattur Industrial Estate"},
    {"name": "Bray Controls India Private Limited", "domain": "bray.com", "sector": "Quarter-Turn Butterfly Valves & Pneumatic Valve Actuators", "primary_hub": "Kancheepuram Chennai"},
    {"name": "Spirax Sarco India Private Limited", "domain": "spiraxsarco.com", "sector": "Steam Traps, Pressure Reducing Valves & Condensate Recovery Units", "primary_hub": "Chennai Maraimalai Nagar"},
    {"name": "Circor Flow Technologies India Private Limited", "domain": "circor.com", "sector": "Severe Service Industrial Control Valves & Safety Relief Valves", "primary_hub": "Coimbatore Tamil Nadu"},

    # Stainless Steel Bars, Bright Steels & Seamless Tubing
    {"name": "Chandan Steel Limited", "domain": "chandansteel.com", "sector": "Stainless Steel Seamless Pipes, Flanges & Heavy Forged Bars", "primary_hub": "Umbergaon Valsad Gujarat"},
    {"name": "Panchmahal Steel Limited", "domain": "panchmahalsteel.co.in", "sector": "Stainless Steel Wire Rods, Cold Finished Bars & Welding Wires", "primary_hub": "Kalol Panchmahal Gujarat"},
    {"name": "Ambica Steels Limited", "domain": "ambicasteels.com", "sector": "Bright Steel Round Bars & Precision Stainless Steel Profiles", "primary_hub": "Sahibabad Ghaziabad Uttar Pradesh"},
    {"name": "Laxcon Steels Limited", "domain": "laxconsteels.com", "sector": "Stainless Steel Round Bars, Bright Bars & Hexagonal Profiles", "primary_hub": "Ahmedabad GIDC Vatva"},
    {"name": "Shah Alloys Limited", "domain": "shahalloys.com", "sector": "Stainless Steel Flat Products & Heavy Alloy Steel Plates", "primary_hub": "Santej Gandhinagar Gujarat"},

    # Industrial Paints, Heavy Protective Coatings & Resins
    {"name": "Kansai Nerolac Paints Limited", "domain": "nerolac.com", "sector": "Industrial Automotive Coatings, Powder Coatings & Coil Coatings", "primary_hub": "Bawal / Lote Parshuram / Hosur"},
    {"name": "Berger Paints India Limited", "domain": "bergerpaints.com", "sector": "Industrial Protective Coatings, Epoxy Floorings & Automotive Coatings", "primary_hub": "Howrah / Rishra / Jejuri Pune"},
    {"name": "Indigo Paints Limited", "domain": "indigopaints.com", "sector": "Emulsion Paints, Enamels & Water-Based Industrial Primers", "primary_hub": "Pudukkottai Tamil Nadu / Jodhpur"},
    {"name": "Shalimar Paints Limited", "domain": "shalimarpaints.com", "sector": "Industrial Marine Protective Coatings & Polyurethane Finishes", "primary_hub": "Nashik Maharashtra / Sikandrabad"},
    {"name": "Akzo Nobel India Limited", "domain": "akzonobel.com", "sector": "International Marine Coatings & Industrial Protective Paints", "primary_hub": "Thane / Gwalior / Hoskote"},

    # Synthetic Latex, Masterbatches & Modified Engineering Plastics
    {"name": "Apcotex Industries Limited", "domain": "apcotex.com", "sector": "Synthetic Latex & High Styrene Synthetic Rubber Plants", "primary_hub": "Taloja Raigad / Valia Bharuch Gujarat"},
    {"name": "Plastiblends India Limited", "domain": "plastiblends.com", "sector": "Color & Additive Masterbatches for Polyolefins & Engineering Plastics", "primary_hub": "Daman / Roorkee / Palsana"},
    {"name": "Kingfa Science & Technology (India) Limited", "domain": "kingfaindia.com", "sector": "Modified Polypropylene Compounds & Engineering Plastics", "primary_hub": "Puducherry / Chakan Pune"},
    {"name": "DHP India Limited", "domain": "dhpindia.com", "sector": "LPG Cylinder Regulators, Brass Valves & Industrial Fittings", "primary_hub": "Howrah West Bengal"},

    # Technical Textiles, High-Tenacity Yarns & Recycled Polyester
    {"name": "Ganesha Ecosphere Limited", "domain": "ganeshaecosphere.com", "sector": "Recycled Polyester Staple Fibre & Spun Yarn Plants", "primary_hub": "Kanpur / Bilaspur / Warangal"},
    {"name": "Banswara Syntex Limited", "domain": "banswarasyntex.com", "sector": "Technical Textiles, Worsted Yarns & Automated Dyeing Plants", "primary_hub": "Banswara Rajasthan"},
    {"name": "Nitin Spinners Limited", "domain": "nitinspinners.com", "sector": "Combed Cotton Yarns, Knitted Fabrics & Finished Wovens", "primary_hub": "Bhilwara Hamirgarh Rajasthan"},
    {"name": "RSWM Limited", "domain": "rswm.in", "sector": "Specialty Synthetic Yarns, Melange Yarns & Co-Gen Power", "primary_hub": "Mandpam Bhilwara Rajasthan"},
    {"name": "Shiva Texyarn Limited", "domain": "shivatex.in", "sector": "Technical Textiles, Coated Fabrics & Tactical Gear", "primary_hub": "Dindigul Tamil Nadu"},

    # Heavy Electrical Grid Switchgear, Generators & Turbines
    {"name": "GE T&D India Limited", "domain": "ge.com", "sector": "Gas Insulated Switchgear, High Voltage Circuit Breakers & Power Transformers", "primary_hub": "Padappai Chennai / Naini Prayagraj"},
    {"name": "ABB India Limited", "domain": "abb.com", "sector": "Robotics Automation, Medium Voltage Switchgear & Induction Motors", "primary_hub": "Peenya Bengaluru / Nelamangala"},
    {"name": "Siemens Limited", "domain": "siemens.com", "sector": "High Voltage Switchgear, Steam Turbines & Rail Traction Equipment", "primary_hub": "Kalwa Thane / Aurangabad"},
    {"name": "Hitachi Energy India Limited", "domain": "hitachienergy.com", "sector": "EHV Power Transformers, Grid Substations & High Voltage Breakers", "primary_hub": "Maneja Vadodara / Peenya"},
    {"name": "Schneider Electric Infrastructure Limited", "domain": "infra.se.com", "sector": "Primary & Secondary Distribution Switchgear & Substation Automation", "primary_hub": "Makarpura Vadodara Gujarat"},
    {"name": "TD Power Systems Limited", "domain": "tdps.co.in", "sector": "AC Generators for Steam, Gas & Hydro Turbines", "primary_hub": "Dabaspet Bengaluru Karnataka"},

    # Industrial Valves, Bronze Fittings & Flow Equipment
    {"name": "Leader Valves Limited", "domain": "leadervalves.com", "sector": "Industrial Cast Steel, Forged Steel & Bronze Valves", "primary_hub": "Jalandhar Punjab"},
    {"name": "Zoloto Valves Private Limited", "domain": "zolotovalves.com", "sector": "Bronze & Cast Steel Gate, Globe & Check Valves", "primary_hub": "Jalandhar Punjab"},
    {"name": "Sant Valves Private Limited", "domain": "santvalves.com", "sector": "Industrial Sluice Valves, Ball Valves & Strainers", "primary_hub": "Jalandhar Punjab"},
    {"name": "Hawa Engineers Limited", "domain": "hawaengineers.com", "sector": "Industrial Gate, Globe, Check, Ball & Butterfly Valves", "primary_hub": "Vatva Ahmedabad Gujarat"},

    # Industrial Gases & Cryogenic Infrastructure
    {"name": "Ellenbarrie Industrial Gases Limited", "domain": "ellenbarrie.com", "sector": "Cryogenic Liquid Oxygen, Nitrogen & Argon Air Separation Plants", "primary_hub": "Uluberia Howrah / Kalyani West Bengal"},
    {"name": "Premier Cryogenics Limited", "domain": "premiercryogenics.com", "sector": "Cryogenic Liquid Nitrogen, Medical Oxygen & Dissolved Acetylene", "primary_hub": "Guwahati Assam"},

    # Automated Packaging, Rigid Containers & Laminated Tubes
    {"name": "Mold-Tek Packaging Limited", "domain": "moldtekpackaging.com", "sector": "In-Mold Labeling Injection Moulded Plastic Containers & Pails", "primary_hub": "Annaram Hyderabad / Satara"},
    {"name": "EPL Limited", "domain": "eplglobal.com", "sector": "Laminated Plastic Packaging Tubes & Dispensing Closures", "primary_hub": "Wada Thane / Chakan / Surat"},
    {"name": "Huhtamaki India Limited", "domain": "huhtamaki.com", "sector": "Specialized Flexible Barrier Laminates & Retort Pouches", "primary_hub": "Silvassa / Hyderabad / Rudrapur"},
    {"name": "TCPL Packaging Limited", "domain": "tcplpack.com", "sector": "High-End Folding Cartons & Rigid Printed Packaging", "primary_hub": "Silvassa / Haridwar / Goa"},

    # Specialized Sterile Injectables & Pharmaceutical Formulations
    {"name": "Gufic Biosciences Limited", "domain": "gufic.com", "sector": "Lyophilized Sterile Injectables & Active Pharmaceutical Ingredients", "primary_hub": "Navsari Gujarat / Belagavi Karnataka"},
    {"name": "Lincoln Pharmaceuticals Limited", "domain": "lincolnpharma.com", "sector": "Solid Orals, Parenteral Solutions & Dry Syrups", "primary_hub": "Khatraj Gandhinagar Gujarat"},
    {"name": "Medicamen Biotech Limited", "domain": "medicamen.com", "sector": "Oncology Injectables, Cytotoxic Formulations & Dry Powder Injections", "primary_hub": "Bhiwadi Rajasthan / Haridwar"},
    {"name": "Jagsonpal Pharmaceuticals Limited", "domain": "jagsonpal.com", "sector": "Gynecology Formulations, Bulk Drugs & Capsules", "primary_hub": "Faridabad Haryana"},
    {"name": "Panacea Biotec Limited", "domain": "panaceabiotec.com", "sector": "Vaccine Formulation Complexes & Recombinant Biopharmaceuticals", "primary_hub": "Baddi Himachal Pradesh / Lalru Punjab"},
    {"name": "Shilpa Medicare Limited", "domain": "shilpamedicare.com", "sector": "Oncology APIs, Peptide Synthesis & Transdermal Patches", "primary_hub": "Raichur Karnataka / Jadcherla Telangana"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_13 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_13.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 13 Clean Companies: {len(final_batch_13)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch13_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 13 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-12)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_13_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_13):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == len(final_batch_13) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {len(final_batch_13)} accounts.")
