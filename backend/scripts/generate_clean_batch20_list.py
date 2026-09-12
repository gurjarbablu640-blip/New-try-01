"""Curates Batch 20 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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
from scripts.prepare_batch19_company_list import BATCH_19_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

all_used_names = set()
for batch in [
    BATCH_100_COMPANIES, BATCH_3_COMPANIES, BATCH_4_COMPANIES, BATCH_5_COMPANIES,
    BATCH_6_COMPANIES, BATCH_7_COMPANIES, BATCH_8_COMPANIES, BATCH_9_COMPANIES,
    BATCH_10_COMPANIES, BATCH_11_COMPANIES, BATCH_12_COMPANIES, BATCH_13_COMPANIES,
    BATCH_14_COMPANIES, BATCH_15_COMPANIES, BATCH_16_COMPANIES, BATCH_17_COMPANIES,
    BATCH_18_COMPANIES, BATCH_19_COMPANIES
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

print(f"Total Unique Accounts Already Evaluated (Batches 25-19): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Group 1: Precision Engineering, Heat Exchangers, Welding & Pre-Engineered
    {"name": "KRN Heat Exchanger and Refrigeration Limited", "domain": "krnheatexchanger.com", "sector": "Fin and Tube Type Heat Exchangers, Condenser Coils & Evaporators", "primary_hub": "Neemrana Alwar Rajasthan"},
    {"name": "Diffusion Engineers Limited", "domain": "diffusionengineers.com", "sector": "Special Purpose Welding Electrodes, Heavy Engineering Equipment & Wear Plates", "primary_hub": "Nagpur Butibori Maharashtra"},
    {"name": "Gala Precision Engineering Limited", "domain": "galagroup.com", "sector": "Disc Springs, Belleville Washers & Special Fasteners for Industrial Turbines", "primary_hub": "Wada Palghar Maharashtra"},
    {"name": "Dee Development Engineers Limited", "domain": "deedevelopment.com", "sector": "Pre-Fabricated Piping Systems, High Pressure Pipe Fittings & Pressure Vessels", "primary_hub": "Palwal Haryana / Numaligarh Assam"},
    {"name": "Interarch Building Products Limited", "domain": "interarchbuildings.com", "sector": "Pre-Engineered Steel Building (PEB) Systems, Metal Roofing & Wall Cladding", "primary_hub": "Pantnagar Uttarakhand / Kichha / Sriperumbudur"},
    {"name": "Ador Welding Limited", "domain": "adorwelding.com", "sector": "Welding Consumables, Flux Cored Wires, CNC Plasma Cutting & Inverter Machines", "primary_hub": "Silvassa / Raipur Chhattisgarh / Pune"},

    # Group 2: Agro Processing, Refineries, Starches & Bio-Organics
    {"name": "Sanstar Limited", "domain": "sanstar.in", "sector": "Maize Starch Derivatives, Liquid Glucose, Dextrose Monohydrate & Sorbitol", "primary_hub": "Shirpur Dhule Maharashtra / Kutch Gujarat"},
    {"name": "Shree Tirupati Balajee Agro Trading Company Limited", "domain": "tirupatibalajee.com", "sector": "FIBC Bulk Bags, Woven Sacks & Polypropylene Industrial Packaging", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Shiva Global Agro Industries Limited", "domain": "shivaglobal.com", "sector": "Single Super Phosphate (SSP) Fertilizers & Granulated Fertilizers", "primary_hub": "Nanded Maharashtra"},
    {"name": "Rama Phosphates Limited", "domain": "ramaphosphates.com", "sector": "SSP Fertilizer, Sulphuric Acid & Soya Solvent Extraction", "primary_hub": "Indore MP / Pune / Udaipur Rajasthan"},
    {"name": "Basant Agro Tech (India) Limited", "domain": "basantagro.com", "sector": "NPK Mixture Fertilizers, SSP & Certified Hybrid Agricultural Seeds", "primary_hub": "Akola Maharashtra"},
    {"name": "Gokul Refoils and Solvent Limited", "domain": "gokulgroup.com", "sector": "Soyabean Oil, Mustard Oil, Castor Oil Derivatives & Edible Refineries", "primary_hub": "Sidhpur Patan Gujarat / Gandhidham Kutch"},
    {"name": "BCL Industries Limited", "domain": "bcl.ind.in", "sector": "Grain-Based Ethanol Distilleries, Edible Oil Refineries & Cattle Feed", "primary_hub": "Bathinda Punjab / Kharagpur West Bengal"},
    {"name": "Vijay Solvex Limited", "domain": "vijaysolvex.com", "sector": "Mustard Oil, Vanaspati Ghee, Soya Refined Oil & Ceramic Insulators", "primary_hub": "Alwar Rajasthan"},
    {"name": "Ajanta Soya Limited", "domain": "ajantasoya.com", "sector": "Refined Palm Oil, Bakery Shortenings, Vanaspati & Edible Fats", "primary_hub": "Bhiwadi Alwar Rajasthan"},

    # Group 3: Pharmaceuticals, APIs & Bulk Formulations
    {"name": "Akums Drugs & Pharmaceuticals Limited", "domain": "akums.net", "sector": "Contract Manufacturing of Oral Liquids, Tablets, Injectables & Dry Syrups", "primary_hub": "Haridwar Uttarakhand"},
    {"name": "Emcure Pharmaceuticals Limited", "domain": "emcure.com", "sector": "Cardiology, Oncology, Antiretroviral Finished Dosage Formulations & APIs", "primary_hub": "Hinjawadi Pune Maharashtra / Sanand / Mehsana"},
    {"name": "Bliss GVS Pharma Limited", "domain": "blissgvs.com", "sector": "Suppositories, Pessaries, Solid Oral Formulations & Syrups", "primary_hub": "Palghar Maharashtra"},
    {"name": "Kwality Pharmaceuticals Limited", "domain": "kwalitypharma.com", "sector": "Lyophilized Injectables, Penicillin Formulations & Oral Solids", "primary_hub": "Amritsar Punjab / Kangra Himachal Pradesh"},
    {"name": "Sanofi India Limited", "domain": "sanofi.in", "sector": "Lantus Insulins, Cardiovascular & Central Nervous System Medications", "primary_hub": "Goa / Ankleshwar Gujarat"},
    {"name": "Paushak Limited", "domain": "paushak.com", "sector": "Phosgene-Based Specialty Chemical Intermediates, Isocyanates & Chloroformates", "primary_hub": "Panelav Panchmahal Gujarat"},
    {"name": "Dharamsi Morarji Chemical Company Limited", "domain": "dmcc.com", "sector": "Sulphuric Acid, Specialty Sulfones, Boron Chemicals & Thionyl Chloride", "primary_hub": "Roha Raigad Maharashtra / Dahej"},
    {"name": "NACL Industries Limited", "domain": "naclind.com", "sector": "Active Technical Pesticides, Fungicides, Herbicides & Agro Formulations", "primary_hub": "Srikakulam Andhra Pradesh / Ethakota"},
    {"name": "Infinium Pharmachem Limited", "domain": "infiniumpharmachem.com", "sector": "Iodine Derivatives, APIs, Curing Agents & Organic Intermediates", "primary_hub": "Sojitra Anand Gujarat"},

    # Group 4: Tyres, Auto Ancillary, Fasteners & Tubing
    {"name": "Tolins Tyres Limited", "domain": "tolinstyres.com", "sector": "Precured Tread Rubber, OTR Tyres, Agricultural Tubes & Retreading Wares", "primary_hub": "Kalady Ernakulam Kerala"},
    {"name": "Igarashi Motors India Limited", "domain": "igarashimotors.com", "sector": "Micro DC Motors, Actuators & Electric Sub-Assemblies for Passenger Vehicles", "primary_hub": "Maraimalai Nagar Chennai Tamil Nadu"},
    {"name": "Mohindra Fasteners Limited", "domain": "mohindra.asia", "sector": "High Tensile Cold Forged Fasteners, Bolts & Screws for Automotive OEMs", "primary_hub": "Rohtak Haryana"},
    {"name": "Pooja Western Metalsiks Limited", "domain": "poojametal.com", "sector": "Brass Valves, Pipe Fittings, Plumbing Hardware & Cast Metallic Couplings", "primary_hub": "Mehsana Gujarat"},
    {"name": "Remi Edelstahl Tubulars Limited", "domain": "remitubes.com", "sector": "Seamless & Welded Stainless Steel Pipes, Heat Exchanger Tubes", "primary_hub": "Tarapur Palghar Maharashtra"},
    {"name": "Suraj Limited", "domain": "surajgroup.com", "sector": "Stainless Steel Seamless Pipes, Tubing & Flanges for Oil & Gas Capex", "primary_hub": "Chhatral Gandhinagar Gujarat"},

    # Group 5: Foundries, Heavy Forgings & Metallics
    {"name": "Rudra Global Infra Products Limited", "domain": "rudraglobal.com", "sector": "Rudra TMT Bars, Structural Billets & Mild Steel Re-rolling Mills", "primary_hub": "Alang Sosiya Bhavnagar Gujarat"},
    {"name": "Sarthak Metals Limited", "domain": "sarthakmetals.com", "sector": "Cored Wires, Aluminium Strontium Alloys & Wire Feeder Machines", "primary_hub": "Bhilai Durg Chhattisgarh"},
    {"name": "Carnation Industries Limited", "domain": "carnationindustries.com", "sector": "Ductile Iron Sanitary Castings, Manhole Covers & Pipe Fittings", "primary_hub": "Uluberia Howrah West Bengal"},
    {"name": "Crescent Foundry Company Private Limited", "domain": "crescentfoundry.in", "sector": "Grey Iron & Ductile Iron Castings, Municipal & Counterweights", "primary_hub": "Kolkata / Uluberia West Bengal / Vadodara"},
    {"name": "Universal Autofoundry Limited", "domain": "ufoundry.com", "sector": "Grey Iron Castings, S.G. Iron Hubs, Brake Drums & Tractor Brackets", "primary_hub": "Reengus Sikar Rajasthan / VKI Jaipur"},
    {"name": "Magna Electro Castings Limited", "domain": "magnacast.com", "sector": "Ductile Iron & Grey Iron Machined Castings for Hydraulic Systems", "primary_hub": "Coimbatore Tamil Nadu"},
    {"name": "Synergy Green Industries Limited", "domain": "synergygreenind.com", "sector": "Heavy Wind Turbine Gearbox Castings, Hollow Rotors & Mining Castings", "primary_hub": "Shiroli Kolhapur Maharashtra"},

    # Group 6: Sugar, Distillery & Bio-Energy
    {"name": "Ugar Sugar Works Limited", "domain": "ugarsugar.com", "sector": "White Crystal Sugar, Cogeneration Power & Industrial Ethyl Alcohol", "primary_hub": "Ugar Khurd Belagavi Karnataka / Jewargi"},
    {"name": "Vishwaraj Sugar Industries Limited", "domain": "vsil.co.in", "sector": "Sugar Milling, Molasses Distillery Ethanol & Bagasse Power Plants", "primary_hub": "Bellad Bagewadi Hukkeri Belagavi Karnataka"},
    {"name": "Sir Shadi Lal Enterprises Limited", "domain": "sirshadilal.com", "sector": "Cane Sugar Extraction, Power Alcohol & Rectified Spirits", "primary_hub": "Shamli Uttar Pradesh"},
    {"name": "Dhampur Bio Organics Limited", "domain": "dhampur.com", "sector": "Refined White Sugar, Industrial Potable Alcohol, Green Energy", "primary_hub": "Asmoli Sambhal / Mansurpur / Meerut UP"},
    {"name": "DCM Shriram Industries Limited", "domain": "dcmsr.com", "sector": "Refined Sugar, Power Cogeneration, Industrial Alcohol & Fine Chemicals", "primary_hub": "Daurala Meerut Uttar Pradesh"},
    {"name": "Gayatri Sugars Limited", "domain": "gayatrisugars.com", "sector": "Plant White Sugar, Molasses Distillation & Bagasse Cogen Energy", "primary_hub": "Kamareddy / Nizamsagar Nizamabad Telangana"},
    {"name": "GM Breweries Limited", "domain": "gmbreweries.com", "sector": "Country Liquor, Rectified Spirit & Blended Grain Alcoholic Beverages", "primary_hub": "Virar Palghar Maharashtra"},
    {"name": "IFB Agro Industries Limited", "domain": "ifbagro.in", "sector": "Grain-Based Alcohol Distilleries, Marine Shrimps & Processed Seafood", "primary_hub": "Noorpur South 24 Parganas West Bengal"},

    # Group 7: Industrial Paper, Technical Textiles & Building Materials
    {"name": "Shree Rama Newsprint Limited", "domain": "ramanewsprint.com", "sector": "Newsprint, Writing & Printing Papers, Recycled Kraft Paper", "primary_hub": "Barbodhan Olpad Surat Gujarat"},
    {"name": "Kuantum Papers Limited", "domain": "kuantumpapers.com", "sector": "Wood-Free Specialty Printing & Writing Papers, Maplitho & Copier Papers", "primary_hub": "Saila Khurd Hoshiarpur Punjab"},
    {"name": "Nitco Limited", "domain": "nitco.in", "sector": "Ceramic Floor Tiles, Vitrified Wall Tiles & Processed Marble Slabs", "primary_hub": "Alibaug Raigad Maharashtra / Silvassa"},
    {"name": "S.P. Apparels Limited", "domain": "spapparels.com", "sector": "Knitted Garments, Organic Cotton Wear, Spinning Mills & Processing Units", "primary_hub": "Avinashi Tirupur Tamil Nadu"},
    {"name": "Zodiac Clothing Company Limited", "domain": "zodiaconline.com", "sector": "Fine Cotton Shirts, Formal Neckwear & High-End Apparel Manufacturing", "primary_hub": "Bengaluru Karnataka / Umbergaon Gujarat"},
    {"name": "Monte Carlo Fashions Limited", "domain": "montecarlo.in", "sector": "Woollen & Cotton Knitwear, Jacquard Fabrics & Garment Finishing Plants", "primary_hub": "Sherpur Ludhiana Punjab"},
    {"name": "Lovable Lingerie Limited", "domain": "lovableindia.in", "sector": "Intimate Apparel, Knitted Undergarments & Precision Stitching Lines", "primary_hub": "Bengaluru Karnataka / Roorkee Uttarakhand"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india|industries)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_20 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_20.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 20 Clean Companies Available: {len(final_batch_20)} (Skipped: {skipped})")

if len(final_batch_20) < 50:
    print(f"ERROR: Only {len(final_batch_20)} companies available, need 50!")
    sys.exit(1)

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch20_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 20 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-19)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_20_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_20[:50]):
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
