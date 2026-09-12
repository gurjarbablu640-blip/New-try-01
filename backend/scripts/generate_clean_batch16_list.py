"""Curates Batch 16 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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
for c in BATCH_14_COMPANIES:
    all_used_names.add(c["name"].lower().strip())
for c in BATCH_15_COMPANIES:
    all_used_names.add(c["name"].lower().strip())

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-15): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Group 1: Sugar, Grain Distilleries & Bio-Alcohols
    {"name": "Piccadily Agro Industries Limited", "domain": "picagro.com", "sector": "Malt Spirit Distilleries, Ethanol Plants & White Crystal Sugar", "primary_hub": "Bhambhewa Jind Haryana / Karnal"},
    {"name": "Som Distilleries & Breweries Limited", "domain": "somindia.com", "sector": "Grain Neutral Alcohol, Malt Spirits & Automated Bottling Plants", "primary_hub": "Rojrachak Raisen Madhya Pradesh / Hassan"},
    {"name": "Globus Spirits Limited", "domain": "globusspirits.com", "sector": "Grain-Based Ethanol Distilleries, DDGS & Industrial Spirits", "primary_hub": "Samalkha Panipat / Behror / Panagarh WB"},
    {"name": "Associated Alcohols & Breweries Limited", "domain": "associatedalcohols.com", "sector": "Extra Neutral Alcohol, Grain-Based Distilleries & Bottling", "primary_hub": "Khargone Madhya Pradesh"},
    {"name": "KM Sugar Mills Limited", "domain": "kmsugar.com", "sector": "White Crystal Sugar, Molasses Distilleries & Bagasse Co-Gen", "primary_hub": "Motinagar Ayodhya Uttar Pradesh"},
    {"name": "Mawana Sugars Limited", "domain": "mawanasugars.com", "sector": "Refined Sugar, Fuel Ethanol & Chemical By-Products", "primary_hub": "Mawana Meerut UP / Titawi Muzaffarnagar"},
    {"name": "Sakthi Sugars Limited", "domain": "sakthisugars.com", "sector": "Sugar Refining, Industrial Alcohol, Soya Products & Power Co-Gen", "primary_hub": "Sakthinagar Erode Tamil Nadu / Sivaganga / Dhenkanal"},
    {"name": "Simbhaoli Sugars Limited", "domain": "simbhaolisugars.com", "sector": "Refined Crystal Sugar, Potable Spirits & Bio-Manure Complexes", "primary_hub": "Simbhaoli Hapur / Brijnathpur UP"},

    # Group 2: Cement Clinker, Slag & Heavy Lime
    {"name": "KCP Limited", "domain": "kcp.co.in", "sector": "Portland Cement Clinker Plants, Heavy Industrial Machinery & Castings", "primary_hub": "Macherla Guntur AP / Muktyala Krishna"},
    {"name": "Udaipur Cement Works Limited", "domain": "udaipurcement.com", "sector": "Platinum Heavy Duty Cement, Clinker Kilns & Grinding Units", "primary_hub": "Shripati Nagar Udaipur Rajasthan"},
    {"name": "Kakatiya Cements Sugar and Industries Limited", "domain": "kakatiyacements.com", "sector": "Ordinary Portland Cement, Clinker Kilns & Crushing Mills", "primary_hub": "Srinivasanagar Dondapadu Nalgonda Telangana"},
    {"name": "Burnpur Cement Limited", "domain": "burnpurcement.com", "sector": "Portland Slag Cement & Clinker Grinding Units", "primary_hub": "Asansol West Bengal / Patratu Jharkhand"},
    {"name": "Shree Digvijay Cement Company Limited", "domain": "digvijaycement.com", "sector": "Kamal Brand Portland Pozzolana Cement & Clinker Plants", "primary_hub": "Digvijaygram Sikka Jamnagar Gujarat"},
    {"name": "Sanghi Industries Limited", "domain": "sanghicement.com", "sector": "Integrated Lignite-based Clinker & Multi-Cements Complex", "primary_hub": "Sanghipuram Abdasa Kutch Gujarat"},

    # Group 3: Glass, Ceramics & Container Packaging
    {"name": "Saint-Gobain Sekurit India Limited", "domain": "sekuritindia.com", "sector": "Laminated Safety Windshields, Tempered Automotive Glass", "primary_hub": "Bhosari Pune / Chakan Maharashtra"},
    {"name": "Empire Industries Limited - Vitrum Glass", "domain": "vitrumglass.com", "sector": "Amber Container Glass Bottles for Pharmaceutical Formulations", "primary_hub": "Vikhroli Mumbai Maharashtra"},
    {"name": "Murudeshwar Ceramics Limited", "domain": "naveentiles.com", "sector": "Naveen Brand Ceramic Floor Tiles, Vitrified Tiles & Glazes", "primary_hub": "Dharwad Karnataka / Karaikal Puducherry"},

    # Group 4: Foundry, Forgings & Precision Heavy Castings
    {"name": "Bhagwati Autocast Limited", "domain": "bhagwati-autocast.com", "sector": "High Duty Grey Iron & SG Iron Castings for Tractors & Earthmovers", "primary_hub": "Bavla Ahmedabad Gujarat"},
    {"name": "Pritika Auto Industries Limited", "domain": "pritikaautoindustries.com", "sector": "Tractor Machined Castings, Axle Housings & Hydraulic Lift Covers", "primary_hub": "Derabassi Mohali Punjab / Hoshiarpur"},
    {"name": "Bedmutha Industries Limited", "domain": "bedmutha.com", "sector": "Galvanized Steel Wire, Copper Wire Rods & Barbed Wires", "primary_hub": "Sinnar Nashik Maharashtra / Dhule"},
    {"name": "RACL Geartech Limited", "domain": "raclgeartech.com", "sector": "Transmission Gears, Shafts & Precision Machined Parts for Motorcycles & Tractors", "primary_hub": "Gajraula Amroha Uttar Pradesh / Noida"},

    # Group 5: Industrial Steel Pipes, Tubing & Oil Country Tubular
    {"name": "Oil Country Tubular Limited", "domain": "octlindia.com", "sector": "Casing Pipes, Tubing & Drill Pipes for Oil & Gas Extraction", "primary_hub": "Narketpally Nalgonda Telangana"},
    {"name": "Zenith Steel Pipes and Industries Limited", "domain": "zenithpipes.com", "sector": "ERW Black & Galvanized Steel Pipes & Structural Tubes", "primary_hub": "Khopoli Raigad Maharashtra / Tarapur"},
    {"name": "Prakash Steelage Limited", "domain": "prakashsteelage.com", "sector": "Stainless Steel Welded & Seamless Pipes & Heat Exchanger Tubes", "primary_hub": "Silvassa / Umbergaon Valsad Gujarat"},

    # Group 6: Dairy, Food Processing & Ice Creams
    {"name": "Hatsun Agro Product Limited", "domain": "hap.in", "sector": "Automated Milk Processing, Arokya Dairy & Ice Cream Plants", "primary_hub": "Kanchipuram / Salem / Palacode Tamil Nadu"},
    {"name": "Allied Blenders and Distillers Limited", "domain": "abdindia.com", "sector": "Automated Grain Neutral Spirit Distilleries & Bottling Complexes", "primary_hub": "Rangapur Telangana / Aurangabad Maharashtra"},
    {"name": "Tilaknagar Industries Limited", "domain": "tilind.com", "sector": "Mansion House Brandy Distilleries & Grain Neutral Spirits", "primary_hub": "Shrirampur Ahmednagar Maharashtra"},

    # Group 7: Synthetic Leather & Footwear Manufacturing
    {"name": "Mayur Uniquoters Limited", "domain": "mayuruniquoters.com", "sector": "Polyvinyl Chloride (PVC) Vinyl Coated Fabric & Synthetic Leather", "primary_hub": "Jaitpura / Dhodsar Jaipur Rajasthan"},
    {"name": "Relaxo Footwears Limited", "domain": "relaxofootwear.com", "sector": "EVA Flip Flops, Polyurethane Footwear & Vulcanized Rubber Shoes", "primary_hub": "Bahadurgarh Haryana / Bhiwadi / Haridwar"},
    {"name": "Campus Activewear Limited", "domain": "campusactivewear.com", "sector": "Athletic Footwear, Phylon Soles & High Frequency Upper Assembly", "primary_hub": "Dehradun / Haridwar Uttarakhand / Baddi"},
    {"name": "Khadim India Limited", "domain": "khadims.com", "sector": "Leather Footwear, Direct Injection Polyurethane Soles & Sandal Units", "primary_hub": "Panpur South 24 Parganas West Bengal / Kasba"},

    # Group 8: Knitted Apparel & Industrial Textiles
    {"name": "Rupa & Company Limited", "domain": "rupa.co.in", "sector": "Knitted Fabric Processing, Automated Cutting & Thermal Wear Plants", "primary_hub": "Domjur Howrah West Bengal / Tirupur"},
    {"name": "Lux Industries Limited", "domain": "luxinnerwear.com", "sector": "Knitted Innerwear, Automated Dyeing & Garment Sewing Units", "primary_hub": "Dankuni Hooghly West Bengal / Tirupur"},
    {"name": "Dollar Industries Limited", "domain": "dollarglobal.in", "sector": "Integrated Spinning, Combed Yarn Knitting & Garment Processing", "primary_hub": "Tirupur Tamil Nadu / Ludhiana Punjab"},

    # Group 9: Specialty Chemicals, Terpenes & High Potency APIs
    {"name": "Mangalam Organics Limited", "domain": "mangalamorganics.com", "sector": "Synthetic Camphor, Terpene Phenolic Resins & Alkyl Phenols", "primary_hub": "Kumbhivali Khalapur Raigad Maharashtra"},
    {"name": "Valiant Organics Limited", "domain": "valiantorganics.com", "sector": "Chlorophenols, Ortho Chloro Phenol & Specialty Fine Chemicals", "primary_hub": "Sarigam / Vapi Gujarat / Tarapur"},
    {"name": "IOL Chemicals and Pharmaceuticals Limited", "domain": "iolcp.com", "sector": "Ibuprofen Active Pharmaceutical Ingredient, Ethyl Acetate & Isobutyl Benzene", "primary_hub": "Barnala Punjab"},
    {"name": "SMS Pharmaceuticals Limited", "domain": "smspharma.com", "sector": "Antiretroviral APIs, Ranitidine HCl & Bulk Drug Intermediates", "primary_hub": "Bollaram / Kazipally Hyderabad Telangana / Vizag"},
    {"name": "Oriental Aromatics Limited", "domain": "orientalaromatics.com", "sector": "Terpene Aroma Chemicals, Camphor & Synthetic Resins", "primary_hub": "Bareilly UP / Vadodara Gujarat / Roha"},
    {"name": "NGL Fine-Chem Limited", "domain": "nglfinechem.com", "sector": "Veterinary Active Pharmaceutical Ingredients & Intermediates", "primary_hub": "Tarapur Thane Maharashtra / Navi Mumbai"},
    {"name": "Dishman Carbogen Amcis Limited", "domain": "dishmangroup.com", "sector": "High Potency APIs, Disinfectants & Phase Transfer Catalysts", "primary_hub": "Bavla Ahmedabad / Naroda Gujarat"},

    # Group 10: Building Products, Fibre Cement & Heavy Plastic Mouldings
    {"name": "Sahyadri Industries Limited", "domain": "silworld.in", "sector": "Swastik Brand Fibre Cement Roofing Sheets & Cem-PR Building Boards", "primary_hub": "Kedgaon Pune / Perundurai Erode / Vijayawada"},
    {"name": "Bigbloc Construction Limited", "domain": "nxtbloc.in", "sector": "NXTBLOC Autoclaved Aerated Concrete (AAC) Lightweight Blocks", "primary_hub": "Umargaon Valsad Gujarat / Wada Palghar / Kapadvanj"},
    {"name": "Flexituff Ventures International Limited", "domain": "flexituff.com", "sector": "Flexible Intermediate Bulk Containers (FIBC), Geotextiles & Woven Sacks", "primary_hub": "Pithampur Dhar Madhya Pradesh / Kashipur"},
    {"name": "Kisan Mouldings Limited", "domain": "kisangroup.com", "sector": "Heavy Agricultural PVC Pipes, Molded Fittings & Solvent Cements", "primary_hub": "Tarapur Maharashtra / Silvassa / Dewas MP"},
    {"name": "Kriti Industries (India) Limited", "domain": "kritiindia.com", "sector": "Kasta Brand Rigid PVC Pipes, Casing Pipes & Micro-Drip Systems", "primary_hub": "Pithampur Dhar Madhya Pradesh"},
    {"name": "Wonder Electricals Limited", "domain": "wonderelectricals.com", "sector": "Ceiling Fans, Exhaust Fans & BLDC Motor Driven Smart Fans", "primary_hub": "Haridwar Uttarakhand / Hyderabad"},
    {"name": "MIC Electronics Limited", "domain": "micelectronics.com", "sector": "LED Video Displays, Railway Information Displays & Oxygen Concentrators", "primary_hub": "Cherlapally Hyderabad Telangana"},
    {"name": "Bilcare Limited", "domain": "bilcare.com", "sector": "Pharmaceutical Barrier Packaging Films, Cold Form Foils & Aluminum Blister Films", "primary_hub": "Rajgurunagar Pune Maharashtra"},
    {"name": "Lloyds Engineering Works Limited", "domain": "lloydsengg.in", "sector": "Heavy Boilers, Pressure Vessels & Marine Deck Machinery", "primary_hub": "Murbad Thane Maharashtra"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india|industries)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_16 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_16.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 16 Clean Companies: {len(final_batch_16)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch16_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 16 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-15)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_16_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_16[:50]):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == min(len(final_batch_16), 50) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {min(len(final_batch_16), 50)} accounts.")
