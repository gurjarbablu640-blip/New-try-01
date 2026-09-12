import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load used companies
from scripts.prepare_100_company_list import BATCH_100_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

with open(b50_path, "r", encoding="utf-8") as f:
    b50_results = json.load(f)["results"]
with open(b25_path, "r", encoding="utf-8") as f:
    b25_results = json.load(f)["results"]

used = set()
for c in BATCH_100_COMPANIES:
    used.add(c["name"].lower().strip())
for r in b50_results:
    used.add(r["company"].lower().strip())
for r in b25_results:
    used.add(r["company"].lower().strip())

# 2. Large pool of brand-new candidate companies across Indian industrial sectors
CANDIDATE_POOL = [
    # Heavy Engineering & Defense
    {"name": "Larsen & Toubro Limited", "domain": "larsentoubro.com", "sector": "Heavy Engineering & Defense", "primary_hub": "Hazira / Powai / Coimbatore"},
    {"name": "Bharat Heavy Electricals Limited", "domain": "bhel.com", "sector": "Power Plant Boilers, Turbines & Transformers", "primary_hub": "Haridwar / Bhopal / Tiruchirappalli"},
    {"name": "Thermax Limited", "domain": "thermaxglobal.com", "sector": "Boilers & Industrial Heating Equipment", "primary_hub": "Pune / Chinchwad / Dahej"},
    {"name": "Kirloskar Oil Engines Limited", "domain": "koel.kirloskar.com", "sector": "Diesel Engines & Gensets", "primary_hub": "Kagal / Kolhapur / Pune"},
    {"name": "Cummins India Limited", "domain": "cummins.com", "sector": "Diesel & Natural Gas Engines", "primary_hub": "Phaltan / Pune / Kothrud"},
    {"name": "TD Power Systems Limited", "domain": "tdps.co.in", "sector": "AC Generators & Steam Turbines", "primary_hub": "Dabaspet / Bengaluru"},

    # Power Transmission & High-Voltage Infrastructure
    {"name": "Voltamp Transformers Limited", "domain": "voltamptransformers.com", "sector": "Power & Distribution Transformers", "primary_hub": "Vadodara / Savli"},
    {"name": "Schneider Electric Infrastructure Limited", "domain": "se.com", "sector": "Medium Voltage Switchgears & Transformers", "primary_hub": "Vadodara / Chennai"},
    {"name": "Apar Industries Limited", "domain": "apar.com", "sector": "Conductors, Transformer Oils & Power Cables", "primary_hub": "Silvassa / Rabale / Khatalwada"},
    {"name": "KEI Industries Limited", "domain": "kei-ind.com", "sector": "Extra High Voltage Cables & Wires", "primary_hub": "Bhiwadi / Chopanki / Silvassa"},
    {"name": "Finolex Cables Limited", "domain": "finolex.com", "sector": "Electrical & Telecommunication Cables", "primary_hub": "Pimpri / Urse / Goa"},

    # Polymers, Industrial Plastics & Packaging
    {"name": "Time Technoplast Limited", "domain": "timetechnoplast.com", "sector": "Industrial Packaging & Composite Cylinders", "primary_hub": "Daman / Silvassa / Mahad"},
    {"name": "EPL Limited", "domain": "eplglobal.com", "sector": "Laminated Plastic Tubes & Packaging", "primary_hub": "Vasind / Wada / Chakan"},
    {"name": "Responsive Industries Limited", "domain": "responsiveindustries.com", "sector": "Vinyl Flooring & Synthetic Leather", "primary_hub": "Boisar / Tarapur"},
    {"name": "Polyplex Corporation Limited", "domain": "polyplex.com", "sector": "Biaxially Oriented Polyester (BOPET) Films", "primary_hub": "Khatima / Bajpur"},
    {"name": "Cosmo First Limited", "domain": "cosmofirst.com", "sector": "Specialty BOPP & CPP Packaging Films", "primary_hub": "Waluj / Shendra / Karjan"},
    {"name": "UFlex Limited", "domain": "uflexltd.com", "sector": "Flexible Packaging & Aseptic Liquid Packaging", "primary_hub": "Noida / Sanand / Jammu"},

    # Medical Devices & Healthcare Manufacturing
    {"name": "Poly Medicure Limited", "domain": "polymedicure.com", "sector": "IV Cannulas & Medical Disposable Devices", "primary_hub": "Faridabad / Haridwar / Jaipur"},
    {"name": "Trivitron Healthcare Private Limited", "domain": "trivitron.com", "sector": "In-Vitro Diagnostics & Medical Imaging", "primary_hub": "Chennai / Irungattukottai"},
    {"name": "Transasia Bio-Medicals Limited", "domain": "transasia.co.in", "sector": "Clinical Chemistry Analyzers & Reagents", "primary_hub": "Mumbai / Baddi / Vizag"},
    {"name": "Hindustan Syringes & Medical Devices Limited", "domain": "hmdhealthcare.com", "sector": "Auto-Disable Syringes & Blood Collection Needles", "primary_hub": "Faridabad"},
    {"name": "Sahajanand Medical Technologies Limited", "domain": "smtpl.com", "sector": "Coronary Stents & Structural Heart Implants", "primary_hub": "Surat / Hyderabad Medical Devices Park"},

    # Consumer Industrial & HVAC Equipment
    {"name": "Blue Star Limited", "domain": "bluestarindia.com", "sector": "Commercial Air Conditioners & Chillers", "primary_hub": "Sri City / Wada / Kala Amb"},
    {"name": "Voltas Limited", "domain": "voltas.com", "sector": "HVAC, Chillers & Commercial Refrigeration", "primary_hub": "Pantnagar / Sanand / Waghodia"},
    {"name": "IFB Industries Limited", "domain": "ifbindustries.com", "sector": "Precision Fine Blanking & Appliances", "primary_hub": "Verna Goa / Bengaluru / Kolkata"},
    {"name": "Symphony Limited", "domain": "symphonylimited.com", "sector": "Commercial & Industrial Evaporative Air Coolers", "primary_hub": "Ahmedabad / Sanand"},
    {"name": "Amber Enterprises India Limited", "domain": "ambergroupindia.com", "sector": "HVAC Components, Heat Exchangers & Sheet Metal", "primary_hub": "Rajpura / Jhajjar / Pune"},
    {"name": "Elin Electronics Limited", "domain": "elinelectronics.com", "sector": "Fractional Horsepower Motors & Lighting", "primary_hub": "Ghaziabad / Baddi / Verna"},

    # Agro-Chemicals & Specialty Formulations
    {"name": "UPL Limited", "domain": "upl-ltd.com", "sector": "Agrochemical Formulations & Technical Actives", "primary_hub": "Ankleshwar / Jhagadia / Vapi"},
    {"name": "Dhanuka Agritech Limited", "domain": "dhanuka.com", "sector": "Crop Protection Chemicals & Technical Formulations", "primary_hub": "Dahej / Sanand / Udhampur"},
    {"name": "Coromandel International Limited", "domain": "coromandel.biz", "sector": "Phosphatic Fertilisers & Crop Nutrition", "primary_hub": "Visakhapatnam / Kakinada / Ennore"},
    {"name": "Chambal Fertilisers and Chemicals Limited", "domain": "chambalfertilisers.com", "sector": "Urea & Nitrogenous Fertilisers", "primary_hub": "Gadapani Kota"},
    {"name": "Deepak Fertilisers and Petrochemicals Corporation Limited", "domain": "dfpcl.com", "sector": "Technical Ammonium Nitrate & Nitric Acid", "primary_hub": "Taloja / Dahej / Srikakulam"},
    {"name": "Rallis India Limited", "domain": "rallis.com", "sector": "Agrochemical Synthesis & Polymer Additives", "primary_hub": "Dahej / Ankleshwar / Akola"},
    {"name": "Bharat Rasayan Limited", "domain": "bharatgroup.co.in", "sector": "Technical Grade Pesticides & Intermediates", "primary_hub": "Dahej / Rohtak"},
    {"name": "Sharda Cropchem Limited", "domain": "shardacropchem.com", "sector": "Agrochemical Formulations & Conveyor Belts", "primary_hub": "Panoli / Ankleshwar"},
    {"name": "India Pesticides Limited", "domain": "indiapesticideslimited.com", "sector": "Active Ingredients & Technical Pesticides", "primary_hub": "Lucknow / Sandila"},
    {"name": "Astec LifeSciences Limited", "domain": "astecls.com", "sector": "Triazole Fungicides & Advanced Intermediates", "primary_hub": "Mahad Raigad"},

    # Industrial Ceramics, Refractories & Abrasives
    {"name": "Carborundum Universal Limited", "domain": "cumi-murugappa.com", "sector": "Bonded Abrasives, Super Refractories & Industrial Ceramics", "primary_hub": "Hosur / Kochi / Ranipet"},
    {"name": "Grindwell Norton Limited", "domain": "grindwellnorton.co.in", "sector": "Precision Abrasives & Performance Refractories", "primary_hub": "Mora / Nagpur / Bengaluru"},
    {"name": "RHI Magnesita India Limited", "domain": "rhimagnesitaindia.com", "sector": "Refractory Products & Systems for Steel Plants", "primary_hub": "Bhiwadi / Cuttack / Visakhapatnam"},
    {"name": "Kajaria Ceramics Limited", "domain": "kajariaceramics.com", "sector": "Vitrified Tiles & Sanitaryware", "primary_hub": "Gailpur / Malootana / Sikandrabad"},
    {"name": "Somany Ceramics Limited", "domain": "somanyceramics.com", "sector": "Ceramic Wall & Floor Tiles", "primary_hub": "Kadi / Bahadurgarh"},

    # Glass & Industrial Packaging
    {"name": "Asahi India Glass Limited", "domain": "aisglass.com", "sector": "Automotive Safety Glass & Architectural Glass", "primary_hub": "Bawal / Chennai / Roorkee"},
    {"name": "AGI Greenpac Limited", "domain": "agigreenpac.com", "sector": "Specialty Glass Packaging & Bottles", "primary_hub": "Sanathnagar / Bhongir"},
    {"name": "Borosil Renewables Limited", "domain": "borosilrenewables.com", "sector": "Solar Glass Manufacturing", "primary_hub": "Govali Jhagadia"},

    # Heavy Electrical, Energy Storage & Power Systems
    {"name": "Amara Raja Energy & Mobility Limited", "domain": "amararaja.com", "sector": "Lead-Acid & Lithium-Ion Giga Factory", "primary_hub": "Tirupati / Divitipally Mahbubnagar"},
    {"name": "Genus Power Infrastructures Limited", "domain": "genuspower.com", "sector": "Smart Electricity Meters & Metering Solutions", "primary_hub": "Jaipur / Haridwar / Guwahati"},
    {"name": "Inox Green Energy Services Limited", "domain": "inoxgreen.com", "sector": "Wind Turbine Operation, Maintenance & Refurbishment", "primary_hub": "Vadodara / Una"},
    {"name": "Orient Green Power Company Limited", "domain": "orientgreenpower.com", "sector": "Biomass & Wind Renewable Generation Equipment", "primary_hub": "Chennai / Pollachi"},
    {"name": "Suzlon Energy Limited", "domain": "suzlon.com", "sector": "Wind Turbine Generators & Hybrid Tower Manufacturing", "primary_hub": "Daman / Chakan / Coimbatore"},
    {"name": "PTC India Financial Services Limited", "domain": "ptcfinancial.com", "sector": "Infrastructure Power Equipment Financing", "primary_hub": "New Delhi"},
    {"name": "Swelect Energy Systems Limited", "domain": "swelectes.com", "sector": "Solar PV Modules & Power Conditioning Units", "primary_hub": "Salem / Coimbatore"},
    {"name": "KEC International Limited (Power T&D)", "domain": "kecrpg.com", "sector": "Extra High Voltage Substations & Railway Traction", "primary_hub": "Vadodara / Butibori"},
    {"name": "HPL Electric & Power Limited", "domain": "hplindia.com", "sector": "Switchgear, Electronic Energy Meters & Wires", "primary_hub": "Gurugram / Kundli / Gharaunda"},
    {"name": "Salzer Electronics Limited", "domain": "salzergroup.net", "sector": "Industrial Rotary Switches & Toroidal Transformers", "primary_hub": "Coimbatore"},
    {"name": "Rishabh Instruments Limited", "domain": "rishabh.co.in", "sector": "Electrical Measurement & Test Instruments", "primary_hub": "Nashik"},
    {"name": "Kaycee Industries Limited", "domain": "kayceeindustries.com", "sector": "Industrial Cam Switches & Counters", "primary_hub": "Ambernath"},
]

# Filter strictly against used set
filtered = []
for c in CANDIDATE_POOL:
    norm = c["name"].lower().strip()
    if norm not in used and not any(u in norm or norm in u for u in ["pi industries", "action construction", "kec international"]):
        filtered.append(c)

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

out_file = os.path.join(os.path.dirname(__file__), "prepare_batch3_company_list.py")
code_content = f'''"""Curated Batch 3 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100)."""
from typing import Dict, List

BATCH_3_COMPANIES: List[Dict[str, str]] = {json.dumps(filtered, indent=4)}

if __name__ == "__main__":
    print(f"Total Batch 3 Companies Prepared: {{len(BATCH_3_COMPANIES)}}")
'''

with open(out_file, "w", encoding="utf-8") as f:
    f.write(code_content)

print(f"Wrote {len(filtered)} companies to {out_file}")
