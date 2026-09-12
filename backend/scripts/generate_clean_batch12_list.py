"""Curates Batch 12 Indian Industrial Manufacturing Companies with guaranteed zero overlap."""
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

if os.path.exists(b50_path):
    with open(b50_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

if os.path.exists(b25_path):
    with open(b25_path, "r", encoding="utf-8") as f:
        for r in json.load(f).get("results", []):
            all_used_names.add(r["company"].lower().strip())

print(f"Total Unique Accounts Already Evaluated (Batches 25-11): {len(all_used_names)}")

CANDIDATE_POOL = [
    # Power Cables & Special Transmission Conductors
    {"name": "Universal Cables Limited", "domain": "unistar.co.in", "sector": "Extra High Voltage XLPE Cables & Capacitors", "primary_hub": "Satna Madhya Pradesh"},
    {"name": "Vindhya Telelinks Limited", "domain": "vtlrewa.com", "sector": "Optical Fibre Cables & Quad Telecom Cables", "primary_hub": "Rewa Madhya Pradesh"},
    {"name": "Birla Cable Limited", "domain": "birlacable.com", "sector": "Telecommunication & Structured Optical Cables", "primary_hub": "Rewa Madhya Pradesh"},
    {"name": "Dynamic Cables Limited", "domain": "dynamiccables.co.in", "sector": "HT/LT Power Cables & Overhead Conductors", "primary_hub": "Jaipur Reengus Rajasthan"},
    {"name": "B whirlpool / Precision Wire India Limited", "domain": "precisionwires.com", "sector": "Enamelled Copper Winding Wires & Strips", "primary_hub": "Silvassa Palej Gujarat"},

    # Specialty Refractories & High Temperature Ceramics
    {"name": "Vesuvius India Limited", "domain": "vesuvius.com", "sector": "Continuous Casting Refractories & Flow Control Ceramics", "primary_hub": "Kolkata / Visakhapatnam"},
    {"name": "RHI Magnesita India Limited", "domain": "rhimagnesita.com", "sector": "Basic Refractory Bricks & Monolithic Mixes", "primary_hub": "Bhiwadi Rajasthan / Jamshedpur"},
    {"name": "IFGL Refractories Limited", "domain": "ifglref.com", "sector": "Specialized Continuous Casting Refractory Systems", "primary_hub": "Rourkela Odisha / Kandla"},
    {"name": "Morgan Advanced Materials India", "domain": "morganadvancedmaterials.com", "sector": "Thermal Ceramics & Carbon Brushes", "primary_hub": "Ranipet Tamil Nadu"},
    {"name": "Orient Refractories Limited", "domain": "orientrefractories.com", "sector": "Continuous Casting Refractories & Nozzles", "primary_hub": "Bhiwadi Alwar Rajasthan"},

    # Cranes, Hoists & Material Handling
    {"name": "Brady & Morris Engineering Company Limited", "domain": "bradymorris.in", "sector": "Electric Overhead Traveling Cranes & Material Hoists", "primary_hub": "Bareja Ahmedabad"},
    {"name": "Hercules Hoists Limited", "domain": "indef.com", "sector": "Indef Brand Chain Pulley Blocks & Electric Wire Rope Hoists", "primary_hub": "Khalapur Maharashtra"},
    {"name": "Kone Elevators India Private Limited", "domain": "kone.in", "sector": "Automated Passenger Elevators & Industrial Escalators", "primary_hub": "Sriperumbudur Chennai"},
    {"name": "Schindler India Private Limited", "domain": "schindler.com", "sector": "Smart Mobility Elevators & Moving Walks", "primary_hub": "Chakan Pune Maharashtra"},
    {"name": "Otis Elevator Company (India) Limited", "domain": "otis.com", "sector": "Commercial & Residential High Speed Elevators", "primary_hub": "Bengaluru Jigani"},

    # Industrial Compressors & Vacuum Systems
    {"name": "Ingersoll Rand (India) Limited", "domain": "ingersollrand.com", "sector": "Centrifugal Industrial Air Compressors & Rotary Screws", "primary_hub": "Naroda Ahmedabad"},
    {"name": "Atlas Copco (India) Limited", "domain": "atlascopco.com", "sector": "Oil-Free Air Compressors & Industrial Vacuum Pumps", "primary_hub": "Dapodi Pune"},
    {"name": "Kaeser Compressors (India) Private Limited", "domain": "kaeser.in", "sector": "Rotary Screw Compressors & Compressed Air Filtration", "primary_hub": "Pune Pirangut"},
    {"name": "HHV - Hind High Vacuum Company Private Limited", "domain": "hhv.in", "sector": "Industrial High Vacuum Equipment & Thin Film Coaters", "primary_hub": "Bengaluru Peenya"},
    {"name": "Toshniwal Instruments (Madras) Private Limited", "domain": "toshniwalindia.com", "sector": "Process Vacuum Pumps & Industrial Powder Mixers", "primary_hub": "Chennai Ambattur"},

    # Precision Seamless Pipes & Cold Drawn Steel
    {"name": "Goodluck India Limited", "domain": "goodluckindia.com", "sector": "Cold Drawn Welded Tubes & High Tensile Forgings", "primary_hub": "Sikandrabad Uttar Pradesh"},
    {"name": "Pennar Industries Limited", "domain": "pennarindia.com", "sector": "Cold Rolled Steel Strips & Precision Hydraulic Tubes", "primary_hub": "Patancheru Hyderabad"},
    {"name": "Steel Exchange India Limited", "domain": "seil.co.in", "sector": "Integrated Steel Plant, Billets & TMT Rebars", "primary_hub": "Visakhapatnam Simhadri"},
    {"name": "Kalyani Steels Limited", "domain": "kalyanisteels.com", "sector": "Forging Quality Alloy Steel Rounds & Blooms", "primary_hub": "Ginigera Koppal Karnataka"},
    {"name": "Sunflag Iron and Steel Company Limited", "domain": "sunflagsteel.com", "sector": "Alloy Steel Bars & Automotive Heavy Flats", "primary_hub": "Bhandara Maharashtra"},

    # Dyes, Pigments & Organic Intermediates
    {"name": "Bodal Chemicals Limited", "domain": "bodal.com", "sector": "Dye Intermediates, Reactive Dyes & Basic Sulphur Acids", "primary_hub": "Padra Vadodara Gujarat"},
    {"name": "Kiri Industries Limited", "domain": "kiriindustries.com", "sector": "Synthetic Organic Dyes & Intermediates Complexes", "primary_hub": "Vadodara Padra Gujarat"},
    {"name": "Bhageria Industries Limited", "domain": "bhageriagroup.com", "sector": "H-Acid, Vinyl Sulphone & Dye Intermediates", "primary_hub": "Vapi Gujarat"},
    {"name": "Dynemic Products Limited", "domain": "dynemic.com", "sector": "Synthetic Food Colors & Specialty Dye Chemicals", "primary_hub": "Ankleshwar Gujarat"},
    {"name": "Vidhi Specialty Food Ingredients Limited", "domain": "vidhifood pageant.com", "sector": "Synthetic Food Grade Colours & Lakes", "primary_hub": "Roha Raigad Maharashtra"},

    # Industrial Packaging Barrels & Bulk Containers
    {"name": "Balmer Lawrie & Company Limited", "domain": "balmerlawrie.com", "sector": "Industrial Steel Barrels, Drum Packaging & Greases", "primary_hub": "Manali Chennai / Silvassa"},
    {"name": "Time Technoplast Limited", "domain": "timetechnoplast.com", "sector": "Industrial Polymer Drums & Composite Intermediate Bulk Containers", "primary_hub": "Silvassa / Mahad"},
    {"name": "Pyramid Technoplast Limited", "domain": "pyramidtechnoplast.com", "sector": "Polymer Drums, IBCs & Heavy Duty Chemical Barrels", "primary_hub": "Bharuch Gujarat"},
    {"name": "TPL Plastech Limited", "domain": "tplplastech.in", "sector": "Industrial Narrow Mouth & Open Top Polymer Drums", "primary_hub": "Silvassa / Ratlam"},
    {"name": "Hitech Corporation Limited", "domain": "hitechgroup.com", "sector": "Rigid Plastic Packaging Containers & Closures", "primary_hub": "Sanand Gujarat / Roorkee"},

    # Industrial Batteries & Power Storage
    {"name": "Amara Raja Energy & Mobility Limited", "domain": "amararaja.com", "sector": "Industrial Lead Acid Batteries & Lithium-Ion Giga Plant", "primary_hub": "Tirupati / Divitipally Telangana"},
    {"name": "HBL Power Systems Limited", "domain": "hbl.in", "sector": "Nickel Cadmium Pocket Plate Batteries & Railway Electronics", "primary_hub": "Shameerpet Hyderabad / Vizag"},
    {"name": "High Energy Batteries (India) Limited", "domain": "highenergy.co.in", "sector": "Silver Zinc Aircraft Batteries & Advanced Storage Cells", "primary_hub": "Mathur Pudukkottai Tamil Nadu"},
    {"name": "Base Corporation Limited", "domain": "basebatteries.com", "sector": "Industrial Standby VRLA Batteries & Power Packs", "primary_hub": "Solan Himachal Pradesh"},
    {"name": "Eveready Industries India Limited", "domain": "evereadyindia.com", "sector": "Dry Cell Batteries, Flashlights & Industrial Lighting", "primary_hub": "Maddock Kolkata / Haridwar"},

    # Industrial Fasteners, Springs & Hardware
    {"name": "Sundram Fasteners Limited", "domain": "sundram.com", "sector": "High Tensile Fasteners & Cold Extruded Parts", "primary_hub": "Padi Chennai / Krishnapuram"},
    {"name": "Sterling Tools Limited", "domain": "stlfasteners.com", "sector": "Special High Tensile Automotive Fasteners", "primary_hub": "Faridabad Haryana / Bengaluru"},
    {"name": "Simmonds Marshall Limited", "domain": "simmondsmarshall.com", "sector": "Nyloc Self-Locking Nuts & Industrial Fasteners", "primary_hub": "Kasarwadi Pune"},
    {"name": "Pooja Forge Limited", "domain": "poojaforge.com", "sector": "Cold Forged Fasteners & Special Precision Screws", "primary_hub": "Faridabad Haryana"},
    {"name": "Precision Camshafts Limited", "domain": "pclindia.in", "sector": "Chilled Cast Iron & Assembled Camshafts", "primary_hub": "Solapur Maharashtra"},

    # Electrical Equipment & Industrial Heaters
    {"name": "BCH Electric Limited", "domain": "bchindia.com", "sector": "Low Voltage Switchgear, Motor Starters & Enclosures", "primary_hub": "Faridabad / Rudrapur"},
    {"name": "Rishabh Instruments Limited", "domain": "rishabh.co.in", "sector": "Analog Panel Meters, Digital Multimeters & Solar Inverters", "primary_hub": "Nashik Maharashtra"},

    # Industrial Ceramics, Tiles & Sanitaryware
    {"name": "Somany Ceramics Limited", "domain": "somanyceramics.com", "sector": "Ceramic Tiles, Vitrified Tiles & Sanitaryware Plants", "primary_hub": "Kadi Gujarat / Kassar Haryana"},
    {"name": "Kajaria Ceramics Limited", "domain": "kajariaceramics.com", "sector": "Glazed Vitrified Tiles & Large Format Ceramic Slabs", "primary_hub": "Gailpur Rajasthan / Malootana"},
    {"name": "Cera Sanitaryware Limited", "domain": "cera-india.com", "sector": "Vitreous China Sanitaryware & Faucets", "primary_hub": "Kadi Mehsana Gujarat"},
    {"name": "Orient Bell Limited", "domain": "orientbell.com", "sector": "Ceramic Wall and Floor Tiles & Polished Vitrified Tiles", "primary_hub": "Sikandrabad Uttar Pradesh / Dora"},
    {"name": "Asian Granito India Limited", "domain": "aglasiangranito.com", "sector": "Ceramic Wall Tiles & Engineered Quartz Slabs", "primary_hub": "Dalpur Himmatnagar Gujarat"},

    # Cement, Lime & Integrated Clinker Complexes
    {"name": "HeidelbergCement India Limited", "domain": "mycemco.com", "sector": "Portland Pozzolana Cement & Integrated Clinker Kilns", "primary_hub": "Damoh Madhya Pradesh / Jhansi"},
    {"name": "Orient Cement Limited", "domain": "orientcement.com", "sector": "Integrated Cement Plants & Slag Grinding Units", "primary_hub": "Devapur Telangana / Chittapur"},
    {"name": "Prism Johnson Limited", "domain": "prismjohnson.in", "sector": "Portland Cement, Ready-Mixed Concrete & Tiles", "primary_hub": "Satna Madhya Pradesh"},
    {"name": "Sagar Cements Limited", "domain": "sagarcements.in", "sector": "Portland Slag Cement & Clinker Rotary Kilns", "primary_hub": "Mattampally Suryapet Telangana"},
    {"name": "NCL Industries Limited", "domain": "nclind.com", "sector": "Nagarjuna Cement & Cement Bonded Particle Boards", "primary_hub": "Simhapuri Suryapet Telangana"},
    {"name": "Mangalam Cement Limited", "domain": "mangalamcement.com", "sector": "Birla Uttam Cement & Clinker Production Units", "primary_hub": "Morak Kota Rajasthan"},

    # Industrial Valves, Process Pumps & Water Equipment
    {"name": "Kirloskar Brothers Limited", "domain": "kirloskarpumps.com", "sector": "Large Centrifugal Pumps, Sluice Valves & Hydropower Turbines", "primary_hub": "Kirloskarvadi Sangli Maharashtra"},
    {"name": "R&D Multiples Valves Private Limited", "domain": "rdmultiples.com", "sector": "Water Supply Butterfly Valves, Kinetic Air Valves & Gate Valves", "primary_hub": "Dombivli Thane Maharashtra"},
    {"name": "G M Engineering Private Limited", "domain": "gmvalve.com", "sector": "Industrial Cast & Forged Steel Ball Valves & Globe Valves", "primary_hub": "Rajkot Gujarat"},
    {"name": "Steelstrong Valves Private Limited", "domain": "steelstrong.com", "sector": "High Pressure Cast Steel Gate, Globe & Check Valves", "primary_hub": "Navi Mumbai Rabale"},

    # Sugar, Distilleries & Biofuels Complexes
    {"name": "Balrampur Chini Mills Limited", "domain": "chini.com", "sector": "Sugar Refining, Co-Generation & Molasses Distilleries", "primary_hub": "Balrampur / Gonda Uttar Pradesh"},
    {"name": "Triveni Engineering & Industries Limited", "domain": "trivenigroup.com", "sector": "High-Speed Industrial Steam Turbines & Sugar Mills", "primary_hub": "Deoband / Naini Prayagraj"},
    {"name": "Dhampur Sugar Mills Limited", "domain": "dhampursugar.com", "sector": "Ethanol Distilleries & Refined Sugar Complexes", "primary_hub": "Dhampur Bijnor Uttar Pradesh"},
    {"name": "Dwarikesh Sugar Industries Limited", "domain": "dwarikesh.com", "sector": "Industrial Sugar & Ethanol Distilleries", "primary_hub": "Bijnor / Bareilly Uttar Pradesh"},
    {"name": "Avadh Sugar & Energy Limited", "domain": "birla-sugar.com", "sector": "Sugar Mills & Co-Gen Power Plants", "primary_hub": "Hargaon Sitapur Uttar Pradesh"},
    {"name": "Dalmia Bharat Sugar and Industries Limited", "domain": "dalmiasugar.com", "sector": "Sugar & Bioethanol Distilleries", "primary_hub": "Nigohi Shahjahanpur Uttar Pradesh"},

    # Industrial Agro Processing, Edible Oils & Marine Infrastructure
    {"name": "Adani Wilmar Limited", "domain": "adaniwilmar.com", "sector": "Edible Oil Refineries & Oleochemical Complexes", "primary_hub": "Mundra Gujarat / Haldia"},
    {"name": "Kriti Nutrients Limited", "domain": "kritinutrients.com", "sector": "Soya Protein & Solvent Extraction Plants", "primary_hub": "Dewas Madhya Pradesh"},
    {"name": "Apex Frozen Foods Limited", "domain": "apexfrozenfoods.in", "sector": "Shrimp Processing & Cold Storage Infrastructure", "primary_hub": "Kakinada Andhra Pradesh"},
    {"name": "Coastal Corporation Limited", "domain": "coastalcorp.co.in", "sector": "Aquaculture Processing & Individual Quick Freezing Plants", "primary_hub": "Visakhapatnam Andhra Pradesh"},

    # Specialty Paper, Pulp & Board Mills
    {"name": "JK Paper Limited", "domain": "jkpaper.com", "sector": "Copier Paper & Virgin Packaging Boards", "primary_hub": "Rayagada Odisha / Songadh Gujarat"},
    {"name": "West Coast Paper Mills Limited", "domain": "westcoastpaper.com", "sector": "Writing & Printing Paper & Industrial Pulp Mills", "primary_hub": "Dandeli Karnataka"},
    {"name": "Andhra Paper Limited", "domain": "andhrapaper.com", "sector": "Pulp & Specialty Paper Manufacturing", "primary_hub": "Rajahmundry Andhra Pradesh"},
    {"name": "Seshasayee Paper and Boards Limited", "domain": "spbltd.com", "sector": "Integrated Pulp and Paper Mills", "primary_hub": "Erode Tamil Nadu"},
    {"name": "Satia Industries Limited", "domain": "satiagroup.com", "sector": "Wood & Agro-Based Writing Paper", "primary_hub": "Muktsar Punjab"},

    # Industrial Food & Grain Processing Infrastructure
    {"name": "LT Foods Limited", "domain": "ltgroup.in", "sector": "Basmati Rice Milling, Silo Storage & Convenience Food Plants", "primary_hub": "Mandideep Bhopal / Kamaspur Sonipat"},
    {"name": "KRBL Limited", "domain": "krblrice.com", "sector": "India Gate Basmati Rice Milling Plants & Parboiling Units", "primary_hub": "Dhuri Punjab / Alipur Delhi"},
    {"name": "Chaman Lal Setia Exports Limited", "domain": "clsel.in", "sector": "Automated Rice Processing & Sortex Cleaning Plants", "primary_hub": "Karnal Haryana"},
    {"name": "GRM Overseas Limited", "domain": "grmrice.com", "sector": "Automated Rice Milling, Processing & Packaging Complexes", "primary_hub": "Panipat Haryana"},

    # Chemical Process Reactors, Glass-Lining & Heat Exchangers
    {"name": "Anup Engineering Limited", "domain": "anupengg.com", "sector": "Shell & Tube Heat Exchangers, Reactors & Pressure Vessels", "primary_hub": "Odhav Ahmedabad Gujarat"},
    {"name": "GMM Pfaudler Limited", "domain": "gmmpfaudler.com", "sector": "Glass-Lined Reactors, Storage Tanks & Wiped Film Evaporators", "primary_hub": "Karamsad Anand Gujarat"},
    {"name": "HLE Glascoat Limited", "domain": "hleglascoat.com", "sector": "Glass-Lined Equipment & Agitated Nutsche Filter Dryers", "primary_hub": "Maroli Navsari / Anand Gujarat"},

    # Ferroalloys, Metallurgical Pellets & Mining Infrastructure
    {"name": "Gujarat Mineral Development Corporation Limited", "domain": "gmdcltd.com", "sector": "Lignite Mining, Bauxite Processing & Fluorspar Beneficiation", "primary_hub": "Panandhro Kutch / Rajpardi"},
    {"name": "MOIL Limited", "domain": "moil.nic.in", "sector": "Manganese Ore Processing & Electrolytic Manganese Dioxide Plants", "primary_hub": "Balaghat Madhya Pradesh / Dongri Buzurg"},
    {"name": "KIOCL Limited", "domain": "kioclltd.in", "sector": "Iron Ore Pellet Plant & Ductile Iron Spun Pipe Plant", "primary_hub": "Mangaluru Panambur Karnataka"},
    {"name": "The Sandur Manganese & Iron Ores Limited", "domain": "sandurgroup.com", "sector": "Silico Manganese, Ferro Manganese & Pig Iron Complex", "primary_hub": "Sandur Ballari Karnataka"},
    {"name": "Maithan Alloys Limited", "domain": "maithanalloys.com", "sector": "Ferro Manganese, Silico Manganese & Ferrosilicon Submerged Arc Furnaces", "primary_hub": "Kalyaneshwari Asansol / Visakhapatnam"},

    # Industrial Footwear & Safety Gear
    {"name": "Superhouse Limited", "domain": "superhouse.co.in", "sector": "Industrial Safety Footwear, Fall Protection & Workwear", "primary_hub": "Unnao Kanpur Uttar Pradesh"},
    {"name": "Liberty Shoes Limited", "domain": "libertyshoes.com", "sector": "Warrior Industrial Safety Footwear & Steel Toe Boots", "primary_hub": "Gharaunda Karnal Haryana"},

    # Plastics Extrusion Machinery & Battery Systems
    {"name": "Kabra Extrusiontechnik Limited", "domain": "kolsite.com", "sector": "Plastics Extrusion Machinery & Battrixx Lithium-Ion Battery Packs", "primary_hub": "Daman Kachigam"},
    {"name": "Windsor Machines Limited", "domain": "windsormachines.com", "sector": "Injection Moulding Machines & Blown Film Extrusion Lines", "primary_hub": "Chhatral Gandhinagar Gujarat"},
    {"name": "Rajoo Engineers Limited", "domain": "rajoo.com", "sector": "Multi-Layer Blown Film Lines & Sheet Extrusion Systems", "primary_hub": "Rajkot Veraval Shapar Gujarat"},

    # Mineral Processing Equipment, Specialized Rubber Liners & Building Infrastructure
    {"name": "Tega Industries Limited", "domain": "tegaindustries.com", "sector": "Mineral Processing Mill Liners, Trommels & Chute Liners", "primary_hub": "Dahej Gujarat / Samali Kolkata"},
    {"name": "HIL Limited", "domain": "hil.in", "sector": "Charminar Fibre Cement Roofing Sheets & Aerocon Autoclaved Aerated Blocks", "primary_hub": "Golan Surat / Faridabad"},
    {"name": "Everest Industries Limited", "domain": "everestind.com", "sector": "Pre-Engineered Steel Buildings & Fibre Cement Boards", "primary_hub": "Podanur Coimbatore / Kymore"},
    {"name": "Visaka Industries Limited", "domain": "visaka.co", "sector": "V-Next Fibre Cement Boards & Asbestos Cement Roofing Sheets", "primary_hub": "Paramathi Namakkal / Medak"}
]

def normalize_name(n: str) -> str:
    n = n.lower().strip()
    n = re.sub(r"\b(limited|ltd|pvt|private|corporation|corp|technologies|tech|solutions|india)\b", "", n)
    return re.sub(r"[^a-z0-9]", "", n)

used_norm = {normalize_name(n) for n in all_used_names}

final_batch_12 = []
skipped = 0
for cand in CANDIDATE_POOL:
    norm = normalize_name(cand["name"])
    if norm in used_norm:
        print(f"Skipping duplicate: {cand['name']}")
        skipped += 1
        continue
    final_batch_12.append(cand)
    used_norm.add(norm)

print(f"\nFinal Batch 12 Clean Companies: {len(final_batch_12)} (Skipped: {skipped})")

out_path = os.path.join(os.path.dirname(__file__), "prepare_batch12_company_list.py")
with open(out_path, "w", encoding="utf-8") as f:
    f.write('"""Curated Batch 12 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 25-11)."""\n')
    f.write("from typing import Dict, List\n\n")
    f.write("BATCH_12_COMPANIES: List[Dict[str, str]] = [\n")
    for i, c in enumerate(final_batch_12):
        f.write("    {\n")
        f.write(f'        "name": "{c["name"]}",\n')
        f.write(f'        "domain": "{c["domain"]}",\n')
        f.write(f'        "sector": "{c["sector"]}",\n')
        f.write(f'        "primary_hub": "{c["primary_hub"]}"\n')
        if i == len(final_batch_12) - 1:
            f.write("    }\n")
        else:
            f.write("    },\n")
    f.write("]\n")

print(f"Successfully generated {out_path} with {len(final_batch_12)} accounts.")
