"""Curates Batch 19 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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
from scripts.prepare_batch14_company_list import BATCH_14_COMPANIES
from scripts.prepare_batch15_company_list import BATCH_15_COMPANIES
from scripts.prepare_batch16_company_list import BATCH_16_COMPANIES
from scripts.prepare_batch17_company_list import BATCH_17_COMPANIES
from scripts.prepare_batch18_company_list import BATCH_18_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

all_used_names = set()
for batch in [
    BATCH_100_COMPANIES, BATCH_3_COMPANIES, BATCH_4_COMPANIES, BATCH_5_COMPANIES,
    BATCH_6_COMPANIES, BATCH_7_COMPANIES, BATCH_8_COMPANIES, BATCH_9_COMPANIES,
    BATCH_10_COMPANIES, BATCH_11_COMPANIES, BATCH_12_COMPANIES, BATCH_13_COMPANIES,
    BATCH_14_COMPANIES, BATCH_15_COMPANIES, BATCH_16_COMPANIES, BATCH_17_COMPANIES,
    BATCH_18_COMPANIES
]:
    for c in batch:
        all_used_names.add(c["name"].lower().strip())

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-18): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Pool 19a (11): Renewable EPC, Polymers, Foods, Agrotech
    {"name": "Gensol Engineering Limited", "domain": "gensol.in", "sector": "Solar EPC Power Plants, Electric Mobility Fleet & EV Manufacturing", "primary_hub": "Chakan Pune Maharashtra / Ahmedabad"},
    {"name": "Sterling and Wilson Renewable Energy Limited", "domain": "sterlingandwilsonre.com", "sector": "Utility Scale Solar EPC, Battery Energy Storage Systems (BESS)", "primary_hub": "Mumbai / Bhadla / Kurnool"},
    {"name": "Zodiac Energy Limited", "domain": "zodiacenergy.com", "sector": "Solar Rooftop EPC, Captive Ground Mounted Solar & EV Chargers", "primary_hub": "Ahmedabad Gujarat"},
    {"name": "Sarda Plywood Industries Limited", "domain": "duroply.in", "sector": "Duro Brand Plywood, Blockboards, Flush Doors & Decorative Veneers", "primary_hub": "Rajkot Gujarat / Jeypore Assam"},
    {"name": "National Plastic Industries Limited", "domain": "nationalplastic.com", "sector": "Moulded Plastic Furniture, Storage Crates & Household Wares", "primary_hub": "Silvassa / Patna / Nellore"},
    {"name": "Creative Plastic Concepts Private Limited", "domain": "creativeplasticconcepts.com", "sector": "Injection Moulded Precision Plastic Components, Medical Crates & Pallets", "primary_hub": "Coimbatore Tamil Nadu"},
    {"name": "Kwality Limited", "domain": "kwality.com", "sector": "Dairy Processing, Pure Ghee, Milk Powders & Pasteurized Pouches", "primary_hub": "Palwal Haryana / Saharanpur UP / Bulandshahr"},
    {"name": "Vadilal Enterprises Limited", "domain": "vadilalgroup.com", "sector": "Ice Creams, Frozen Desserts, Processed Frozen Vegetables & Ready-to-Eat", "primary_hub": "Pundhra Gandhinagar Gujarat / Bareilly UP"},
    {"name": "Bafna Pharmaceuticals Limited", "domain": "bafnapharma.com", "sector": "Non-Beta Lactam Solid Oral Formulations, Tablets & Suspensions", "primary_hub": "Madhavaram Chennai Tamil Nadu"},
    {"name": "Coral Laboratories Limited", "domain": "corallab.com", "sector": "Pharmaceutical Formulations, Beta Lactam Injectables & Syrups", "primary_hub": "Dehradun Uttarakhand / Daman"},
    {"name": "Kilpest India Limited", "domain": "kilpest.com", "sector": "Molecular Diagnostic Kits, PCR Reagents & Agro Chemical Pesticides", "primary_hub": "Govindpura Bhopal Madhya Pradesh"},

    # Pool 19b (4): Industrial Coatings & Specialty Metallics
    {"name": "Sheenlac Paints Limited", "domain": "sheenlac.com", "sector": "Wood Coatings, Decorative Paints, Industrial Thinners & Polyurethane Primers", "primary_hub": "Ambattur Chennai Tamil Nadu"},
    {"name": "Manaksia Coated Metals & Industries Limited", "domain": "manaksiacoatedmetals.com", "sector": "Pre-painted Galvanised Steel Sheets, Color Coated Coils & Profiles", "primary_hub": "Kutch Gandhidham Gujarat"},
    {"name": "Manaksia Steels Limited", "domain": "manaksiasteels.com", "sector": "Cold Rolled Steel Coils, Galvanised Corrugated Sheets & Metal Tiles", "primary_hub": "Haldia Purba Medinipur West Bengal"},
    {"name": "Manaksia Aluminium Company Limited", "domain": "manaksiaaluminium.com", "sector": "Aluminium Rolled Sheets, Coils, Aluminium Circles & Patterned Tread Plates", "primary_hub": "Haldia West Bengal"},

    # Pool 19c (4): EV Chargers, Axles, Transmissions & Aquaculture Processing
    {"name": "Exicom Tele-Systems Limited", "domain": "exicom.in", "sector": "EV Fast Chargers, Telecom Power Systems & Lithium-ion Battery Packs", "primary_hub": "Gurugram Haryana / Solan HP"},
    {"name": "Kross Limited", "domain": "krosslimited.com", "sector": "Trailer Axle Assemblies, Suspension Kits & Forged Tractor Heavy Parts", "primary_hub": "Adityapur Jamshedpur Jharkhand"},
    {"name": "Divgi TorqTransfer Systems Limited", "domain": "divgi-tts.com", "sector": "Transfer Cases, Torque Couplers, Dual-Clutch Automatic Transmission Gears", "primary_hub": "Bhosari Pune / Shirwal / Shivane Maharashtra"},
    {"name": "Waterbase Limited", "domain": "waterbaseindia.com", "sector": "Shrimp Aquaculture Feeds, Hatchery Larval Diets & Processed Seafood", "primary_hub": "Nellore Andhra Pradesh"},

    # Pool 19e (8): Signaling, Rail Bogies, Solar Modules & Specialty Chemicals
    {"name": "Kernex Microsystems (India) Limited", "domain": "kernex.in", "sector": "Kavach Train Collision Avoidance Systems, Railway Signaling & Axle Counters", "primary_hub": "Hardware Park Shamshabad Hyderabad Telangana"},
    {"name": "Cosmic CRF Limited", "domain": "cosmiccrf.com", "sector": "Cold Rolled Stainless Steel Profiles, Railway Freight Wagon Sub-Assemblies", "primary_hub": "Singur Hooghly West Bengal"},
    {"name": "Bondada Engineering Limited", "domain": "bondada.net", "sector": "Telecom Towers, Solar EPC Engineering & Precast Concrete Substructures", "primary_hub": "Keesara Medchal Hyderabad Telangana"},
    {"name": "Solex Energy Limited", "domain": "solex.in", "sector": "High-Efficiency Mono PERC & TOPCon Solar PV Modules", "primary_hub": "Tadkeshwar Surat Gujarat"},
    {"name": "Alpex Solar Limited", "domain": "alpexsolar.com", "sector": "Photovoltaic Solar Modules, High Capacity Solar Water Pumping Systems", "primary_hub": "Surajpur Greater Noida Uttar Pradesh"},
    {"name": "Sharat Industries Limited", "domain": "sharatindustries.com", "sector": "Shrimp Aquaculture Processing, Cold Storage & Frozen Value-Added Seafood", "primary_hub": "Nellore Andhra Pradesh"},
    {"name": "Jubilant Ingrevia Limited", "domain": "jubilantingrevia.com", "sector": "Specialty Pyridine Derivatives, Acetyls, Nutrition Precursors & Fine Chemicals", "primary_hub": "Gajraula Amroha UP / Bharuch Gujarat"},
    {"name": "Godavari Biorefineries Limited", "domain": "godavaribiorefineries.com", "sector": "Bio-based Specialty Chemicals, Ethanol Distillation & Cane Sugar Byproducts", "primary_hub": "Sameerwadi Bagalkot Karnataka / Sakarwadi Maharashtra"},

    # Pool 19f (6): Steel, Rebars, Lubricants & Petroleum Derivatives
    {"name": "Kamdhenu Limited", "domain": "kamdhenulimited.com", "sector": "Kamdhenu Brand TMT Rebars, Structural Steel & Pre-Engineered Steel Frames", "primary_hub": "Bhiwadi Alwar Rajasthan"},
    {"name": "Visa Steel Limited", "domain": "visasteel.com", "sector": "High Carbon Ferro Chrome, Sponge Iron, Pig Iron & Captive Power Plants", "primary_hub": "Kalinganagar Jajpur Odisha"},
    {"name": "Savita Oil Technologies Limited", "domain": "savita.com", "sector": "Transformer Oils, Liquid Paraffins, White Oils & Industrial Synthetic Lubricants", "primary_hub": "Turbhe Navi Mumbai / Silvassa / Mahad"},
    {"name": "Gulf Oil Lubricants India Limited", "domain": "gulfoilindia.com", "sector": "Commercial Vehicle Lubricants, 2-Wheeler Engine Oils & Industrial Greases", "primary_hub": "Silvassa / Ennore Chennai Tamil Nadu"},
    {"name": "Tide Water Oil Co. (India) Limited", "domain": "tidewaterindia.com", "sector": "Veedol Brand Automotive Engine Oils, Industrial Gear Lubricants & Greases", "primary_hub": "Turbhe Navi Mumbai / Howrah / Oragadam Chennai"},
    {"name": "Panama Petrochem Limited", "domain": "panamapetro.com", "sector": "Petroleum Jelly, White Mineral Oils, Rubber Process Oils & Transformer Fluids", "primary_hub": "Ankleshwar Gujarat / Daman / Taloja"},

    # Pool 19g (8): Mineral Oils, Adhesives, Footwear & Starch Refineries
    {"name": "Gandhar Oil Refinery (India) Limited", "domain": "gandharoil.com", "sector": "Divyol Brand White Mineral Oils, Automotive Lubricants & Process Oils", "primary_hub": "Taloja Raigad Maharashtra / Silvassa"},
    {"name": "Chembond Chemicals Limited", "domain": "chembondindia.com", "sector": "Industrial Water Treatment Chemicals, Protective Coatings, Adhesives & Sealants", "primary_hub": "Tarapur Palghar Maharashtra / Dudhwada Vadodara"},
    {"name": "Paragon Polymer Products Private Limited", "domain": "paragonfootwear.com", "sector": "EVA Rubber Footwear, Polyurethane Soles & Vulcanized Footwear", "primary_hub": "Kottayam Kerala / Bengaluru / Surat"},
    {"name": "VKC Group Footwear Private Limited", "domain": "vkcgroup.com", "sector": "VKC Pride PU Footwear, Lightweight Sandals & Micro-Cellular Rubber Soles", "primary_hub": "Kozhikode Calicut Kerala / Coimbatore TN"},
    {"name": "Leayan Global Private Limited", "domain": "redtape.com", "sector": "RedTape Leather Footwear, Vulcanized Rubber Soles & Tanning Plants", "primary_hub": "Unnao Uttar Pradesh / Noida"},
    {"name": "Tirupati Starch & Chemicals Limited", "domain": "tirupatistarch.com", "sector": "Maize Starch Powder, Dextrines, Liquid Glucose & Maize Gluten Byproducts", "primary_hub": "Sejwaya Ghatabillod Dhar Madhya Pradesh"},
    {"name": "Riddhi Siddhi Gluco Biols Limited", "domain": "riddhisiddhi.co.in", "sector": "Corn Wet Milling, High Fructose Syrups & Agro Processing Facilities", "primary_hub": "Gokak Belagavi Karnataka / Pantnagar"},
    {"name": "Oriental Trimex Limited", "domain": "orientaltrimex.com", "sector": "Imported Marble Processing, Granite Slabs Cutting & Polishing Plants", "primary_hub": "Greater Noida UP / Gummidipoondi TN"},

    # Pool 19h (6): Asphalt, Construction Bitumen, Polymer Additives & Flexo Machines
    {"name": "Agarwal Industrial Corporation Limited", "domain": "agarwalindustrial.com", "sector": "Industrial Bitumen, Crumb Rubber Modified Bitumen (CRMB) & Bituminous Emulsions", "primary_hub": "Taloja Raigad Maharashtra / Vadodara / Belagavi"},
    {"name": "STP Limited", "domain": "stpltd.com", "sector": "ShaliSeal Joint Sealants, Waterproofing Membranes & Protective Bitumen Coatings", "primary_hub": "Hooghly West Bengal / Kosi Kalan UP / Panoli"},
    {"name": "Tiki Tar Industries Private Limited", "domain": "tikitardriveways.com", "sector": "Polymer Modified Bitumen, Cold Mix Asphalt & Pavement Crack Sealants", "primary_hub": "Halol Vadodara Gujarat"},
    {"name": "Bhansali Engineering Polymers Limited", "domain": "bhansaliabs.com", "sector": "Acrylonitrile Butadiene Styrene (ABS) Resins & Polycarbonate-ABS Blends", "primary_hub": "Abu Road Sirohi Rajasthan / Satnoor MP"},
    {"name": "Rotomac Industries Private Limited", "domain": "rotomac.com", "sector": "Industrial Rewinding Equipment, Continuous Rotor Casting & Transformer Coil Winders", "primary_hub": "Kanpur Uttar Pradesh"},
    {"name": "Flexo Image Graphics Private Limited", "domain": "figworld.biz", "sector": "Flexographic Printing Machinery, Narrow Web Label Presses & Plate Making Systems", "primary_hub": "Noida Uttar Pradesh"},

    # Pool 19i: Verified Free Industrial Manufacturing Candidates
    {"name": "Ujaas Energy Limited", "domain": "ujaas.com", "sector": "Solar Power Plants, Rooftop Solar EPC & Power Transformers", "primary_hub": "Sanwer Road Indore Madhya Pradesh"},
    {"name": "Diamond Power Infrastructure Limited", "domain": "dicabs.com", "sector": "Power Transmission Cables, Conductors & Power Transformers", "primary_hub": "Vadodara Gujarat"},
    {"name": "Tara Chand Infralogistic Solutions Limited", "domain": "tarachandindia.in", "sector": "Heavy Infrastructure Equipment Fabrication & Heavy Lifting Cranes", "primary_hub": "Chandigarh / Navi Mumbai"},
    {"name": "Surana Solar Limited", "domain": "suranasolar.com", "sector": "Solar Photovoltaic Modules & Solar EPC Projects", "primary_hub": "Cherlapally Hyderabad Telangana"},
    {"name": "Urja Global Limited", "domain": "urjaglobal.in", "sector": "Solar Panels, Lithium-ion Battery Packs & E-Rickshaw Assemblies", "primary_hub": "Greater Noida Uttar Pradesh"},
    {"name": "India Glycols Limited", "domain": "indiaglycols.com", "sector": "Green Chemicals, Bio-Monoethylene Glycol & Industrial Gases", "primary_hub": "Kashipur Uttarakhand / Gorakhpur UP"},
    {"name": "TGV SRAAC Limited", "domain": "tgvgroup.com", "sector": "Caustic Soda, Chlorine, Castor Oil Derivatives & Fatty Acids", "primary_hub": "Kurnool Andhra Pradesh / Bellary"},
    {"name": "MSP Steel & Power Limited", "domain": "mspsteel.com", "sector": "TMT Rebars, Structural Steel, Sponge Iron & Billets", "primary_hub": "Raigarh Chhattisgarh"},
    {"name": "Pennar Industries Limited", "domain": "pennarindia.com", "sector": "Cold Rolled Steel Strips, Precision Tubes & Solar Mounting Structures", "primary_hub": "Patancheru Hyderabad Telangana / Chennai"},
    {"name": "Sharda Motor Industries Limited", "domain": "shardamotor.com", "sector": "Exhaust Systems, Suspension Systems & Catalytic Converters", "primary_hub": "Greater Noida UP / Chennai / Sanand"},
    {"name": "Lumax Auto Technologies Limited", "domain": "lumaxworld.in", "sector": "Integrated Plastic Modules, 2-Wheeler Chassis & Gear Shifters", "primary_hub": "Pune Maharashtra / Manesar / Pantnagar"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india|industries)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_19 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_19.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 19 Clean Companies Available: {len(final_batch_19)} (Skipped: {skipped})")

if len(final_batch_19) < 50:
    print(f"ERROR: Only {len(final_batch_19)} companies available, need 50!")
    sys.exit(1)

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch19_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 19 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-18)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_19_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_19[:50]):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == 49:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with 50 unique accounts.")
