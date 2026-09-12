import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 1. Load all used companies across all previous batches
from scripts.prepare_100_company_list import BATCH_100_COMPANIES
from scripts.prepare_batch3_company_list import BATCH_3_COMPANIES
from scripts.prepare_batch4_company_list import BATCH_4_COMPANIES

b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
b25_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_25_audit_results.json")

used = set()
for c in BATCH_100_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_3_COMPANIES:
    used.add(c["name"].lower().strip())
for c in BATCH_4_COMPANIES:
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

# 2. Candidate Pool for Batch 5 (Tires/Rubber, Paints/Coatings, Food/Beverage, FMCG Manufacturing)
CANDIDATE_POOL = [
    # Auto Ancillaries — Tires & Industrial Rubber
    {"name": "MRF Limited", "domain": "mrftyres.com", "sector": "Radial Tires, Conveyor Belting & Pre-Treads", "primary_hub": "Arakkonam / Kottayam / Tiruvottiyur / Medak"},
    {"name": "Apollo Tyres Limited", "domain": "apollotyres.com", "sector": "Commercial & Passenger Vehicle Radial Tires", "primary_hub": "Perambra / Limda Vadodara / Chennai / Ennore"},
    {"name": "CEAT Limited", "domain": "ceat.com", "sector": "High Performance Tires & Off-Highway Tires", "primary_hub": "Halol / Nagpur / Ambernath / Bhandup"},
    {"name": "JK Tyre & Industries Limited", "domain": "jktyre.com", "sector": "Truck/Bus Radial (TBR) Tires & Retreading", "primary_hub": "Kankroli Rajsamand / Mysuru / Banmore / Haridwar"},
    {"name": "Balkrishna Industries Limited", "domain": "bkt-tires.com", "sector": "Off-Highway Agricultural & Mining Tires", "primary_hub": "Waluj / Bhiwadi / Chopanki / Bhuj"},
    {"name": "TVS Srichakra Limited", "domain": "tvseurogrip.com", "sector": "Two-Wheeler & Off-Road Industrial Tires", "primary_hub": "Madurai Vellaripatti / Pantnagar"},
    {"name": "Goodyear India Limited", "domain": "goodyear.co.in", "sector": "Farm & Passenger Car Radial Tires", "primary_hub": "Ballabgarh Faridabad"},

    # Industrial Paints & Specialty Coatings
    {"name": "Asian Paints Limited", "domain": "asianpaints.com", "sector": "Decorative Coatings, Industrial Resins & Pre-Treatment", "primary_hub": "Ankleshwar / Kasna Greater Noida / Sriperumbudur / Rohtak / Khandala / Mysuru / Vizag"},
    {"name": "Berger Paints India Limited", "domain": "bergerpaints.com", "sector": "Industrial Protective Coatings & Powder Coatings", "primary_hub": "Howrah / Rishra / Pondicherry / Goa / Jammu / Sandila Lucknow"},
    {"name": "Kansai Nerolac Paints Limited", "domain": "nerolac.com", "sector": "Automotive OEM Coatings & High Performance Polyurethanes", "primary_hub": "Lote Parshuram / Bawal / Jainpur / Hosur / Sayakha / Goindwal"},
    {"name": "Akzo Nobel India Limited", "domain": "akzonobel.co.in", "sector": "Marine Coatings, Specialty Chemicals & Aerospace Finishes", "primary_hub": "Thane / Gwalior / Bengaluru Hoskote"},
    {"name": "Indigo Paints Limited", "domain": "indigopaints.com", "sector": "Water-Based Emulsions & Cement Paints", "primary_hub": "Jodhpur / Kochi Pudukkottai"},
    {"name": "Sirca Paints India Limited", "domain": "sircapaints.com", "sector": "Wood Coatings, Melamine & Polyurethane Finishes", "primary_hub": "Sonipat Haryana"},

    # Food & Beverage Processing & Cold Chain Infrastructure
    {"name": "Britannia Industries Limited", "domain": "britannia.co.in", "sector": "Bakery, Dairy & Automated Food Processing", "primary_hub": "Bidadi / Ranjangaon / Jhagadia / Perundurai / Gwalior"},
    {"name": "Nestle India Limited", "domain": "nestle.in", "sector": "Prepared Dishes, Milk Products & Confectionery", "primary_hub": "Moga / Choladi / Nanjangud / Samalkha / Ponda / Tahliwal / Sanand"},
    {"name": "Varun Beverages Limited", "domain": "varunbeverages.com", "sector": "Carbonated Soft Drinks, Juices & Packaged Water Bottling", "primary_hub": "Greater Noida / Kosi / Pathankot / Sandila / Gorakhpur"},
    {"name": "Bikaji Foods International Limited", "domain": "bikaji.com", "sector": "Ethnic Snacks, Sweets & Frozen Food Processing", "primary_hub": "Bikaner Karni / Tumakuru / Muzaffarpur"},
    {"name": "Mrs. Bectors Food Specialities Limited", "domain": "cremica.in", "sector": "Biscuits, Bakery & Condiments Manufacturing", "primary_hub": "Phillaur / Tahliwal / Rajpura / Greater Noida / Khopoli"},
    {"name": "LT Foods Limited", "domain": "ltgroup.in", "sector": "Milled Rice, Convenience Food & Organic Grain Processing", "primary_hub": "Kamaspur Sonipat / Mandideep Bhopal / Varpal Amritsar"},
    {"name": "KRBL Limited", "domain": "krblrice.com", "sector": "Paddy Milling, Grain Grading & Biomass Cogeneration", "primary_hub": "Dhuri Sangrur / Alipur Delhi"},
    {"name": "ADF Foods Limited", "domain": "adf-foods.com", "sector": "Meal Accompaniments, Pickles & Frozen Food Packaging", "primary_hub": "Nadiad / Bharuch"},
    {"name": "CCL Products (India) Limited", "domain": "cclproducts.com", "sector": "Soluble Instant Coffee & Spray Dried Agglomeration", "primary_hub": "Duggirala Guntur / Chittoor"},
    {"name": "Avanti Feeds Limited", "domain": "avantifeeds.com", "sector": "Crustacean Feeds & Modern Shrimp Processing", "primary_hub": "Kovvur West Godavari / Bandapuram"},
    {"name": "Apex Frozen Foods Limited", "domain": "apexfrozenfoods.in", "sector": "Ready-to-Cook Aquatic Food & Blast Freezing", "primary_hub": "Kakinada / Ragampeta"},

    # Personal Care, Oleochemicals & FMCG Manufacturing
    {"name": "Hindustan Unilever Limited", "domain": "hul.co.in", "sector": "Soaps, Detergents, Oral Care & Industrial Formulations", "primary_hub": "Haridwar / Dapada Silvassa / Khamgaon / Sumerpur / Chhindwara / Doom Dooma"},
    {"name": "Dabur India Limited", "domain": "dabur.com", "sector": "Ayurvedic Medicines, Personal Care & Fruit Juices", "primary_hub": "Baddi / Sahibabad / Pantnagar / Tezpur / Pithampur"},
    {"name": "Marico Limited", "domain": "marico.com", "sector": "Edible Oils, Hair Care & Deodorant Formulations", "primary_hub": "Kanjikode Palakkad / Perundurai / Baddi / Jalgaon / Paonta Sahib"},
    {"name": "Emami Limited", "domain": "emamiltd.in", "sector": "Personal Care & Healthcare Formulations", "primary_hub": "Abhaypur Guwahati / Pantnagar / Vapi / Dongari"},
    {"name": "Bajaj Consumer Care Limited", "domain": "bajajconsumercare.com", "sector": "Cosmetics & Hair Oil Formulations", "primary_hub": "Paonta Sahib / Dehradun / Guwahati"},
    {"name": "Jyothy Labs Limited", "domain": "jyothylabs.com", "sector": "Fabric Whiteners, Dishwash & Mosquito Repellents", "primary_hub": "Pithampur / Kanjikode / Pondicherry / Roorkee / Baddi"},
    {"name": "Gillette India Limited", "domain": "pg.com", "sector": "Blades, Razors & Precision Personal Care Hardware", "primary_hub": "Bhiwadi Alwar / Baddi"},
    {"name": "Procter & Gamble Hygiene and Health Care Limited", "domain": "pg.com", "sector": "Feminine Hygiene & Healthcare Formulations", "primary_hub": "Mandideep Bhopal / Baddi"},

    # Industrial Gases & Cryogenic Process Equipment
    {"name": "Linde India Limited", "domain": "linde.in", "sector": "Cryogenic Air Separation Plants & Medical Oxygen Cylinders", "primary_hub": "Taloja / Srikakulam / Bellary / Rourkela / Dahej"},
    {"name": "Refex Industries Limited", "domain": "refex.co.in", "sector": "Refrigerant Gas Refilling & Industrial Gas Handling", "primary_hub": "Thiruporur Chennai"},

    # Packaging, Metal Cans & Closures
    {"name": "Hindustan Tin Works Limited", "domain": "hindustantin.biz", "sector": "Printed Metal Cans & Components for Food/Paints", "primary_hub": "Murthal Sonipat"},
    {"name": "Kaira Can Company Limited", "domain": "kairacan.com", "sector": "Open Top Sanitary Cans & Metal Containers", "primary_hub": "Anand Gujarat / Kanjari"},

    # Electrical Wires, Switchgear & Smart Meters
    {"name": "Polycab India Limited", "domain": "polycab.com", "sector": "Wires, Power Cables, Fast Moving Electrical Goods", "primary_hub": "Halol Panchmahal / Daman / Nashik"},
    {"name": "Havells India Limited", "domain": "havells.com", "sector": "Switchgear, Cables, Motors & Consumer Electricals", "primary_hub": "Alwar / Baddi / Haridwar / Neemrana / Faridabad / Sahibabad"},

    # Additional FMCG, Dairy, Food & Sugar/Ethanol Processing Plants
    {"name": "ITC Limited", "domain": "itcportal.com", "sector": "Paperboards, Packaging, Agri-Business & Branded Foods", "primary_hub": "Bhadrachalam / Tribeni / Haridwar / Mysuru / Munger"},
    {"name": "Godrej Consumer Products Limited", "domain": "godrejcp.com", "sector": "Household Insecticides, Soaps & Personal Wash", "primary_hub": "Malanpur / Guwahati / Baddi / Pondicherry"},
    {"name": "Colgate-Palmolive (India) Limited", "domain": "colgatepalmolive.co.in", "sector": "Oral Care Formulations & Toothbrush Molding", "primary_hub": "Sanand / Baddi / Goa / Sri City"},
    {"name": "Tata Consumer Products Limited", "domain": "tataconsumer.com", "sector": "Packaged Tea, Salt Refining & Food Formulations", "primary_hub": "Munnar / Durgapur / Bengaluru"},
    {"name": "Prataap Snacks Limited", "domain": "yellowdiamond.in", "sector": "Extruded Snacks, Potato Chips & Namkeen", "primary_hub": "Indore / Guwahati / Thane"},
    {"name": "DFM Foods Limited", "domain": "dfmfoods.com", "sector": "Corn Rings & Wheat-Based Extruded Snacks", "primary_hub": "Greater Noida / Kashipur"},
    {"name": "Heritage Foods Limited", "domain": "heritagefoods.in", "sector": "Pasteurized Milk, Curd, Paneer & Dairy Powders", "primary_hub": "Chittoor / Shamirpet / Bayyavaram"},
    {"name": "Dodla Dairy Limited", "domain": "dodladairy.com", "sector": "Liquid Milk Processing & UHT Sterilization", "primary_hub": "Nellore / Penumuru / Kurnool"},
    {"name": "Parag Milk Foods Limited", "domain": "paragmilkfoods.com", "sector": "Processed Cheese, Paneer & Whey Proteins", "primary_hub": "Manchar Pune / Palamaner Chittoor"},
    {"name": "Zydus Wellness Limited", "domain": "zyduswellness.com", "sector": "Nutritional Powders, Table Margarine & Skincare", "primary_hub": "Aligarh / Sitarganj / Ahmedabad"},
    {"name": "Avadh Sugar & Energy Limited", "domain": "birla-sugar.com", "sector": "Sugar Processing, Fuel Ethanol & Bio-Power", "primary_hub": "Hargaon Sitapur / Seohara Bijnor / Hata Kushinagar"},
    {"name": "Magadh Sugar & Energy Limited", "domain": "birla-sugar.com", "sector": "Sugar Refining & Molasses-Based Distillery", "primary_hub": "Narkatiaganj West Champaran / Hasanpur Samastipur"},
    {"name": "Uttam Sugar Mills Limited", "domain": "uttamsugar.in", "sector": "Sugar Processing & High-Yield Bioethanol", "primary_hub": "Libberheri Roorkee / Barkatpur / Khaikheri"},
    {"name": "Dwarikesh Sugar Industries Limited", "domain": "dwarikesh.com", "sector": "Cane Crushing, Ethanol Distillation & Power", "primary_hub": "Dwarikesh Nagar Bijnor / Dwarikesh Puram Bareilly"},
    {"name": "Bajaj Hindusthan Sugar Limited", "domain": "bajajhindusthan.com", "sector": "Integrated Sugar, Fuel Ethanol & Bio-Electricity", "primary_hub": "Golagokarannath Kheri / Palia Kalan / Barkhera"},
    {"name": "Gokaldas Exports Limited", "domain": "gokaldasexports.com", "sector": "Apparel & Garment Manufacturing Plants", "primary_hub": "Bengaluru / Mysuru"},
    {"name": "Sutlej Textiles and Industries Limited", "domain": "sutlejtextiles.com", "sector": "Specialty Dyed Yarns & Melange Fabrics", "primary_hub": "Bhawanimandi / Kathua / Baddi"},
    {"name": "Somany Impresa Limited", "domain": "somanyimpresa.com", "sector": "Sanitaryware & Glass Packaging", "primary_hub": "Bahadurgarh / Bibinagar"},
]

# Filter strictly against used set
filtered = []
for c in CANDIDATE_POOL:
    norm = c["name"].lower().strip()
    if norm not in used and not any(u == norm for u in used):
        filtered.append(c)

print(f"Total Candidate Pool: {len(CANDIDATE_POOL)}")
print(f"Total Filtered Clean Candidates: {len(filtered)}")

out_file = os.path.join(os.path.dirname(__file__), "prepare_batch5_company_list.py")
code_content = f'''"""Curated Batch 5 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25, 50, 100, 3, 4)."""
from typing import Dict, List

BATCH_5_COMPANIES: List[Dict[str, str]] = {json.dumps(filtered, indent=4)}

if __name__ == "__main__":
    print(f"Total Batch 5 Companies Prepared: {{len(BATCH_5_COMPANIES)}}")
'''

with open(out_file, "w", encoding="utf-8") as f:
    f.write(code_content)

print(f"Wrote {len(filtered)} companies to {out_file}")
