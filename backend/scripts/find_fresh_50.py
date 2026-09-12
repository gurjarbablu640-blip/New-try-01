import glob
import os
import re

scripts_dir = os.path.dirname(os.path.abspath(__file__))
script_files = glob.glob(os.path.join(scripts_dir, "prepare_batch*_company_list.py")) + glob.glob(os.path.join(scripts_dir, "prepare_100_company_list.py"))
prior_names = set()
for sf in script_files:
    with open(sf, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r'"name":\s*"([^"]+)"', line)
            if m:
                prior_names.add(m.group(1).lower().strip())

print(f"Total existing unique companies: {len(prior_names)}")

# Let's inspect which sectors or patterns are already heavily covered.
# Let's write a large pool of 150 real Indian manufacturers from BSE/NSE SME/Midcap
pool = [
    ("Alicon Castalloy Limited", "alicongroup.com", "Aluminium Castings & Cylinder Heads", "Chakan Pune"),
    ("Auto Corporation of Goa Limited", "acglgoa.com", "Bus Bodies & Sheet Metal Components", "Bhuimpal Sattari Goa"),
    ("Automotive Stampings and Assemblies Limited", "autostampings.com", "Sheet Metal Stampings & Welded Assemblies", "Bhosari Pune / Halol Gujarat"),
    ("Bimetal Bearings Limited", "bimite.co.in", "Engine Bearings, Bushings & Thrust Washers", "Coimbatore / Hosur Tamil Nadu"),
    ("Commercial Engineers & Body Builders Co Limited", "cebbco.com", "Railway Wagons & Heavy Commercial Vehicle Bodies", "Jabalpur Madhya Pradesh"),
    ("Duroflex Private Limited", "duroflexworld.com", "Polyurethane Foam & Industrial Mattresses", "Hosur Tamil Nadu"),
    ("Enkei Wheels (India) Limited", "enkei.in", "Aluminium Alloy Wheels for Passenger Cars", "Shikrapur Pune Maharashtra"),
    ("Federal-Mogul Goetze (India) Limited", "federalmogulgoetze.in", "Pistons, Piston Rings & Sintered Products", "Patiala Punjab / Bengaluru"),
    ("GKN Driveline (India) Limited", "gknautomotive.com", "Constant Velocity Joints & Driveline Systems", "Dharuhera Haryana / Oragadam"),
    ("GNA Gears Limited", "gnagears.com", "Automotive Transmission Gears & Shafts", "Phagwara Punjab"),
    ("Hi-Tech Gears Limited", "thehitechgears.com", "Engine Precision Gears & Transmission Components", "Bhiwadi Rajasthan / Manesar"),
    ("India Motor Parts and Accessories Limited", "impal.net", "Automobile Parts Distribution & Logistics", "Chennai Tamil Nadu"),
    ("IP Rings Limited", "iprings.com", "Piston Rings & Transmission Orbital Cold Formed Parts", "Maraimalai Nagar Chennai"),
    ("Jamna Auto Industries Limited", "jaispring.com", "Automotive Tapered Leaf Springs & Parabolic Springs", "Yamunanagar / Malanpur / Jamshedpur"),
    ("Kross Limited", "krossindia.com", "Trailer Axles, Suspension Assemblies & Forged Components", "Adityapur Jamshedpur Jharkhand"),
    ("L.G. Balakrishnan & Bros Limited", "lgb.co.in", "Roller Chains, Sprockets & Industrial Conveyor Belts", "Coimbatore Tamil Nadu"),
    ("MENON Bearings Limited", "menonbearings.com", "Bi-metal Engine Bearings, Bushings & Thrust Washers", "MIDC Shiroli Kolhapur Maharashtra"),
    ("Menon Pistons Limited", "menonpistons.com", "Aluminium Alloy Pistons & Gudgeon Pins", "Shiroli Kolhapur Maharashtra"),
    ("Munjal Auto Industries Limited", "munjalauto.com", "Exhaust Systems, Steel Wheel Rims & Fuel Tanks", "Waghodia Vadodara / Bawal Haryana"),
    ("Munjal Showa Limited", "munjalshowa.net", "Shock Absorbers & Struts for Two-Wheelers & Cars", "Gurugram Haryana / Haridwar"),
    ("Omax Autos Limited", "omaxauto.com", "Commercial Vehicle Chassis Frames & Sheet Metal Stampings", "Dharuhera / Bawal Haryana"),
    ("Prabhat Technologies (India) Limited", "prabhatgroup.net", "Telecom Products & Mobile Accessories", "Mumbai Maharashtra"),
    ("Precision Camshafts Limited", "pclindia.com", "Chilled Cast Iron & Assembled Camshafts", "Solapur Maharashtra"),
    ("Pritika Auto Industries Limited", "pritikaautoindustries.com", "Tractor Machined Castings & Transmission Cases", "Derabassi Mohali Punjab"),
    ("Rane Engine Valve Limited", "ranegroup.com", "Engine Valves, Valve Guides & Mechanical Tappets", "Viralimalai / Hyderabad / Chennai"),
    ("Remsons Industries Limited", "remsons.com", "Auto Control Cables, Gear Shift Systems & Winches", "Daman / Gurugram / Pune"),
    ("Samkrg Pistons and Rings Limited", "samkrg.com", "Pistons, Piston Pins & Piston Rings", "Bonthapally Hyderabad Telangana"),
    ("Shivani Detergents Private Limited", "shivanidetergents.com", "Industrial Detergents & Surfactants", "Indore Madhya Pradesh"),
    ("Sharda Motor Industries Limited", "shardamotor.com", "Automotive Exhaust Systems & Catalytic Converters", "Greater Noida UP / Chennai"),
    ("Shivam Autotech Limited", "shivamautotech.com", "Transmission Gears, Spline Shafts & Starter Gears", "Gurugram / Haridwar / Rohtak"),
    ("Standard Radiators Limited", "standardradiators.com", "Heat Exchangers, Industrial Radiators & Oil Coolers", "Vadodara Gujarat"),
    ("Steel Strips Wheels Limited", "sswlindia.com", "Steel & Alloy Wheel Rims for Passenger Cars & Trucks", "Dappar Punjab / Chennai / Mehsana"),
    ("Talbros Automotive Components Limited", "talbros.com", "Automotive Gaskets, Heat Shields & Forgings", "Faridabad Haryana / Pune / Sitarganj"),
    ("Ucal Fuel Systems Limited", "ucalfuel.com", "Fuel Injection Systems, Carburetors & Vacuum Pumps", "Maraimalai Nagar Chennai / Puducherry"),
    ("Varroc Engineering Limited", "varroc.com", "Polymer Molding, Exterior Lighting & Engine Valves", "Waluj Chhatrapati Sambhaji Nagar / Pune"),
    ("GTL Infrastructure Limited", "gtlinfra.com", "Telecom Tower Passive Infrastructure", "Navi Mumbai Maharashtra"),
    ("Vakrangee Limited", "vakrangee.in", "E-Governance Services & Hardware Terminals", "Mumbai Maharashtra"),
    ("Nelco Limited", "nelco.co.in", "VSAT Satellite Communication Hardware & Maritime Comms", "Mahape Navi Mumbai"),
    ("Websol Energy System Limited", "websol.energy", "Solar Photovoltaic Cells & Monocrystalline PV Modules", "Falta SEZ West Bengal"),
    ("Premier Energies Limited", "premierenergies.com", "Solar Cells & Solar Photovoltaic Module Assembly", "Maheshwaram Hyderabad Telangana"),
    ("Waaree Energies Limited", "waaree.com", "Solar Panels, Inverters & Solar Thermal Products", "Surat / Chikhli Gujarat / Greater Noida"),
    ("Vikram Solar Limited", "vikramsolar.com", "High-Efficiency Solar Modules & EPC Solutions", "Oragadam Chennai / Falta West Bengal"),
    ("Inox Wind Limited", "inoxwind.com", "Wind Turbine Generators, Nacelles & Rotor Blades", "Rohika Ahmedabad / Barwani MP"),
    ("Suzlon Energy Limited", "suzlon.com", "Wind Turbines, Tubular Steel Towers & Hybrid Lattice", "Daman / Chakan Pune / Bhuj Gujarat"),
    ("Orient Green Power Company Limited", "orientgreenpower.com", "Wind Energy Generation & Substation Equipment", "Chennai Tamil Nadu"),
    ("KPI Green Energy Limited", "kpigreenenergy.com", "Solar Power Plants & Wind-Solar Hybrid Parks", "Bharuch Gujarat"),
    ("Sterling and Wilson Renewable Energy Limited", "sterlingandwilsonre.com", "Utility-Scale Solar EPC & Energy Storage", "Mumbai Maharashtra"),
    ("Borosil Renewables Limited", "borosilrenewables.com", "Low Iron Solar Glass & Patterned Antireflective Glass", "Govali Jhagadia Bharuch Gujarat"),
    ("Adani Green Energy Limited", "adanigreenenergy.com", "Solar & Wind Power Plants & Hybrid Energy Parks", "Khavda Kutch Gujarat"),
    ("Tata Power Solar Systems Limited", "tatapowersolar.com", "Solar Cell & Module Manufacturing & Microgrids", "Tirunelveli Tamil Nadu / Bengaluru"),
    ("Goldi Solar Private Limited", "goldisolar.com", "Solar PV Modules, Micro-Inverters & Cell Assembly", "Navsari Gujarat / Surat"),
    ("Emmvee Photovoltaic Power Private Limited", "emmvee.com", "Solar PV Modules, Water Heaters & Clean Energy", "Dasanapura Bengaluru Karnataka"),
    ("RenewSys India Private Limited", "renewsysworld.com", "Solar Encapsulants (EVA/POE) & Backsheets", "Patalganga Maharashtra / Hyderabad"),
    ("Alpex Solar Limited", "alpexsolar.com", "Solar PV Modules, AC/DC Solar Water Pumps", "Greater Noida Uttar Pradesh"),
    ("Zodiac Energy Limited", "zodiacenergy.com", "Rooftop Solar & Captive Solar Power Solutions", "Ahmedabad Gujarat"),
    ("SJVN Limited", "sjvn.nic.in", "Hydro Electric Power, Solar Power & Transmission", "Shimla Himachal Pradesh"),
    ("NHPC Limited", "nhpcindia.com", "Hydroelectric Power Generation & Substation Infra", "Faridabad Haryana"),
    ("THDC India Limited", "thdc.co.in", "Hydro Power Projects & Thermal Power Stations", "Rishikesh Uttarakhand"),
    ("NEEPCO Limited", "neepco.co.in", "Hydro & Thermal Power Plants in North East", "Shillong Meghalaya"),
    ("NTPC Green Energy Limited", "ntpc.co.in", "Renewable Energy Parks & Green Hydrogen Hubs", "New Delhi"),
    ("Nava Limited", "navalimited.com", "Ferro Alloys, Power Generation & Sugar Refining", "Paloncha Kothagudem Telangana / Odisha"),
    ("Tata Steel Long Products Limited", "tatasteellp.com", "Sponge Iron, Special Steel Billets & Wire Rods", "Gamharia Jamshedpur Jharkhand"),
    ("Jai Balaji Industries Limited", "jaibalajigroup.com", "Ductile Iron Pipes, Sponge Iron, Pig Iron & Steel", "Durgapur / Raniganj West Bengal"),
    ("Kalyani Steels Limited", "kalyanisteels.com", "Forging Quality Carbon & Alloy Steels for Autos", "Ginigera Koppal Karnataka / Pune"),
    ("Sunflag Iron and Steel Company Limited", "sunflagsteel.com", "Special Alloy Steel Rounds, Billets & Hexagons", "Bhandara Maharashtra"),
    ("Steel Exchange India Limited", "seil.co.in", "TMT Rebars, Sponge Iron & Billet Rolling Mills", "Kothapeta Visakhapatnam Andhra Pradesh"),
    ("Mukand Limited", "mukand.com", "Specialty Stainless Steel, Alloy Steel & Cranes", "Thane Maharashtra / Hospet Karnataka"),
    ("Usha Martin Limited", "ushamartin.com", "Steel Wire Ropes, Strands, Optical Fibre & Aircraft Cables", "Ranchi Jharkhand / Hoshiarpur"),
    ("Bedmutha Industries Limited", "bedmutha.com", "Galvanized Steel Wires, Tyre Bead Wire & Copper Wires", "Nardana Dhule / Sinnar Nashik Maharashtra"),
    ("Rajratan Global Wire Limited", "rajratan.co.in", "Tyre Bead Wire & High Carbon Steel Wire", "Pithampur Dhar Madhya Pradesh / Thailand"),
    ("Geekay Wires Limited", "geekaywires.com", "Galvanized Iron Wires, Binding Wires & Nails", "Hyderabad Telangana"),
    ("DP Wires Limited", "dpwires.co.in", "LRPC Steel Wires, Induction Hardened Wires", "Ratlam Madhya Pradesh"),
    ("Deccan Cements Limited", "deccancements.com", "Specialty Clinker, Portland Slag Cement", "Bhavanipuram Nalgonda Telangana"),
    ("NCL Industries Limited", "nclind.com", "Cement, Bison Particle Boards & AAC Blocks", "Mattapalli Suryapet Telangana / Kondapalli"),
    ("Sagar Cements Limited", "sagarcements.in", "Ordinary Portland Cement & Portland Pozzolana Cement", "Mattampally Suryapet Telangana / Bayyavaram"),
    ("KCP Limited", "kcp.co.in", "Heavy Engineering Machinery, Heavy Castings & Sugar", "Tiruvottiyur Chennai Tamil Nadu / Macherla AP"),
    ("Anjani Portland Cement Limited", "anjanicement.com", "Composite Cement, Rapid Hardening Cement", "Chintalapalem Suryapet Telangana"),
    ("Mangalam Cement Limited", "mangalamcement.com", "Portland Pozzolana Cement & Quick Setting Cement", "Morak Kota Rajasthan"),
    ("Udaipur Cement Works Limited", "udaipurcement.com", "Portland Cement & Clinker Production", "Shripad Nagar Udaipur Rajasthan"),
    ("Shiva Cement Limited", "shivacement.com", "Clinker Grinding & Portland Slag Cement", "Kutra Sundargarh Odisha"),
    ("Burnpur Cement Limited", "burnpurcement.com", "Portland Slag Cement & Grinding Units", "Asansol West Bengal / Patratu Jharkhand"),
    ("Kakatiya Cement Sugar and Industries Limited", "kakatiyacements.com", "Cement Manufacturing & White Crystal Sugar", "Peruvancha Khammam Telangana"),
    ("Shree Digvijay Cement Company Limited", "digvijaycement.com", "Marine Coastal Cement & Sulphate Resistant Cement", "Digvijaygram Sikka Jamnagar Gujarat"),
    ("Indo Farm Equipment Limited", "indofarm.in", "Tractors & Heavy Construction Machinery", "Baddi Solan Himachal Pradesh"),
    ("Captain Tractors Private Limited", "captaintractors.com", "Mini Tractors & Agricultural Implements", "Rajkot Gujarat"),
    ("Tirth Agro Technology Private Limited", "shaktimanagro.com", "Agricultural Implements & Rotary Tillers", "Rajkot Gujarat"),
    ("Action Construction Equipment Limited", "ace-cranes.com", "Hydraulic Mobile Cranes & Construction Equipment", "Faridabad Haryana"),
    ("Revathi Equipment Limited", "revathi.in", "Blast Hole Drilling Rigs & Water Well Drills", "Coimbatore Tamil Nadu"),
    ("The Anup Engineering Limited", "anupengg.com", "Heat Exchangers, Reactors & Pressure Vessels", "Odhav Ahmedabad Gujarat"),
    ("Walchandnagar Industries Limited", "walchand.com", "Defense, Nuclear Power Equipment & Gearboxes", "Walchandnagar Pune Maharashtra"),
    ("Isgec Heavy Engineering Limited", "isgec.com", "Process Equipment, Industrial Boilers & Presses", "Yamunanagar Haryana / Dahej"),
    ("Kennametal India Limited", "kennametal.com", "Tungsten Carbide Tooling & Machining Solutions", "Bengaluru Karnataka"),
    ("Wendt (India) Limited", "wendtindia.com", "Superabrasive Grinding Wheels & Honing Machines", "Hosur Tamil Nadu"),
    ("Disa India Limited", "disagroup.com", "Foundry Machinery & Shot Blasting Equipment", "Tumakuru Bengaluru Karnataka"),
    ("Ingersoll Rand (India) Limited", "ingersollrand.com", "Industrial Air Compressors & Blowers", "Naroda Ahmedabad Gujarat"),
    ("Mazda Limited", "mazdalimited.com", "Vacuum Systems, Evaporators & Control Valves", "Naroda Ahmedabad Gujarat"),
    ("Everest Kanto Cylinder Limited", "everestkanto.com", "High Pressure Seamless Gas & CNG Cylinders", "Gandhidham Gujarat / Tarapur"),
    ("Confidence Petroleum India Limited", "confidencegroup.co", "LPG Cylinders & Auto LPG Dispensing Stations", "Nagpur Maharashtra"),
    ("Pennar Industries Limited", "pennarindia.com", "Pre-Engineered Buildings & Cold Rolled Steel", "Patancheru Hyderabad Telangana"),
    ("Salasar Techno Engineering Limited", "salasartechno.com", "Telecom Towers, Transmission Lines & Poles", "Hapur Uttar Pradesh"),
    ("Skipper Limited", "skipperlimited.com", "Power Transmission Towers & Polymer Pipes", "Uluberia Howrah West Bengal"),
    ("Goodluck India Limited", "goodluckindia.com", "Forged Flanges, CR Coils & Transmission Towers", "Sikandrabad Bulandshahr UP"),
    ("Man Industries (India) Limited", "mangroup.com", "LSAW & HSAW Large Diameter Carbon Steel Pipes", "Anjar Kutch Gujarat / Pithampur"),
    ("Venus Pipes & Tubes Limited", "venuspipes.com", "Stainless Steel Seamless & Welded Pipes", "Dhaneti Bhuj Kutch Gujarat"),
    ("Rama Steel Tubes Limited", "ramasteel.com", "Galvanized Steel Pipes & Tubes", "Sahibabad Ghaziabad UP / Khopoli"),
    ("Hi-Tech Pipes Limited", "hitechpipes.in", "Steel Hollow Sections, Solar Mounting Structures", "Sikandrabad UP / Sanand Gujarat"),
    ("MM Forgings Limited", "mmforgings.com", "Automotive Steel Forgings & Machined Components", "Singaperumal Koil Chennai / Viralimalai"),
    ("Nitin Spinners Limited", "nitinspinners.com", "Cotton Yarns, Knitted Fabrics & Finished Woven", "Bhilwara Rajasthan"),
    ("Ambika Cotton Mills Limited", "acmlindia.com", "Compact Cotton Yarn for Export & Weaving", "Dindigul Tamil Nadu"),
    ("Shiva Texyarn Limited", "shivatex.in", "Technical Textiles, Coated Fabrics & Garments", "Coimbatore Tamil Nadu"),
    ("Precot Limited", "precot.com", "Cotton Yarn, Threads & Nonwoven Hygiene Fabrics", "Kanjikode Palakkad Kerala / Coimbatore"),
    ("Nahar Industrial Enterprises Limited", "owmnahar.com", "Yarns, Fabrics & Garments", "Lalru SAS Nagar Punjab / Ambala"),
    ("Himatsingka Seide Limited", "himatsingka.com", "Bedding, Bath Linen & Drapery Fabrics", "Hassan Karnataka / Doddaballapur"),
    ("Gokaldas Exports Limited", "gokaldasexports.com", "Apparel & Outerwear Manufacturing", "Yeshwanthpur Bengaluru Karnataka"),
    ("Dollar Industries Limited", "dollarglobal.in", "Knitted Hosiery & Innerwear", "Tirupur Tamil Nadu / Kolkata"),
    ("Rupa & Company Limited", "rupa.co.in", "Hosiery Garments & Casual Wear", "Jalan Industrial Complex Howrah / Tirupur"),
    ("Lux Industries Limited", "luxinnerwear.com", "Hosiery & Knitwear Garment Production", "Dankuni Hooghly West Bengal / Tirupur"),
    ("Shreyans Industries Limited", "shreyansgroup.com", "Writing & Printing Paper & Cotton Yarn", "Ahmedgarh Sangrur Punjab"),
    ("Star Paper Mills Limited", "starpapers.com", "Industrial & Packaging Paper Grades", "Saharanpur Uttar Pradesh"),
    ("Ruchira Papers Limited", "ruchirapapers.com", "Kraft Paper & Writing Printing Paper", "Kala Amb Sirmaur Himachal Pradesh"),
    ("Satia Industries Limited", "satiagroup.com", "Wood & Agro-Based Printing Paper", "Muktsar Punjab"),
    ("Pudumjee Paper Products Limited", "pudumjee.com", "Specialty Papers & Crepe Tissue", "Thergaon Pune Maharashtra"),
    ("TCPL Packaging Limited", "tcplpack.com", "Folding Cartons, Flexible Packaging & Barrier Films", "Silvassa / Haridwar / Goa"),
    ("Mold-Tek Packaging Limited", "moldtekpackaging.com", "Injection Molded Rigid Plastic Packaging & IML", "Annaram Medak Hyderabad / Daman"),
    ("Cosmo First Limited", "cosmofirst.com", "BOPP & CPP Specialty Films", "Waluj Aurangabad / Karjan Vadodara"),
    ("Ester Industries Limited", "esterindustries.com", "Polyester Films & Engineering Plastics", "Khatima Udham Singh Nagar Uttarakhand"),
    ("Shilchar Technologies Limited", "shilchargroup.com", "Distribution & Power Transformers", "GIDC Bil Vadodara Gujarat"),
    ("Transformers and Rectifiers (India) Limited", "transformerindia.com", "Power & Furnace Transformers", "Changodar Ahmedabad Gujarat"),
    ("Voltamp Transformers Limited", "voltamptransformers.com", "Oil Filled & Dry Type Power Transformers", "Makarpura Vadodara Gujarat"),
    ("TD Power Systems Limited", "tdps.co.in", "AC Generators & Steam Turbine Generators", "Dabaspet Bengaluru Karnataka"),
    ("Bharat Bijlee Limited", "bharatbijlee.com", "Transformers, Electric Motors & Drives", "Airoli Navi Mumbai Maharashtra"),
    ("Macpower CNC Machines Limited", "macpowercnc.com", "CNC Lathes, Machining Centers & Turning Centers", "Metoda GIDC Rajkot Gujarat"),
    ("Jyoti CNC Automation Limited", "jyoti.co.in", "Multi-Axis Machining Centers & High Precision CNC", "GIDC Lodhika Metoda Rajkot"),
    ("Lokesh Machines Limited", "lokeshmachines.com", "Special Purpose Machines & CNC Machine Tools", "Balanagar Hyderabad Telangana"),
    ("AIA Engineering Limited", "aiaengineering.com", "High Chrome Grinding Media & Mill Liners", "Moraiya Ahmedabad Gujarat"),
    ("Elecon Engineering Company Limited", "elecon.com", "Material Handling Equipment & Industrial Gears", "Vallabh Vidyanagar Anand Gujarat"),
    ("Dynamatic Technologies Limited", "dynamatics.com", "Aerospace Hydraulic & Precision Engineering", "Peenya Bengaluru Karnataka"),
    ("Kirloskar Brothers Limited", "kirloskarpumps.com", "Centrifugal Pumps, Valves & Hydroturbines", "Kirloskarvadi Sangli Maharashtra"),
    ("Praj Industries Limited", "praj.net", "Bioenergy, Critical Process Equipment & Breweries", "Kandla Gujarat / Sanaswadi Pune"),
    ("Banco Products (India) Limited", "bancoindia.com", "Engine Cooling Systems & Gaskets", "Bil Vadodara Gujarat"),
    ("Subros Limited", "subros.com", "Automotive Air Conditioning Systems & Thermal Products", "Noida UP / Manesar Haryana"),
    ("Lumax Industries Limited", "lumaxworld.in", "Automotive Lighting Systems", "Dharuhera / Gurugram / Pune"),
    ("Suprajit Engineering Limited", "suprajit.com", "Mechanical Control Cables & Halogen Lamps", "Bommasandra Bengaluru Karnataka"),
    ("Sandhar Technologies Limited", "sandhargroup.com", "Automotive Locking Systems & Die Casting", "Gurugram Haryana / Bawal"),
    ("Gabriel India Limited", "anandgroupindia.com", "Ride Control Products & Shock Absorbers", "Chakan Pune Maharashtra"),
    ("Pricol Limited", "pricol.com", "Instrument Clusters, Telematics & Oil Pumps", "Perianaickenpalayam Coimbatore"),
    ("Craftsman Automation Limited", "craftsmanautomation.com", "Powertrain Machining & Storage Systems", "Coimbatore Tamil Nadu / Pune"),
]






print(f"Total pool items: {len(pool)}")
valid_unique = []
for name, dom, sec, hub in pool:
    nl = name.lower().strip()
    if nl not in prior_names:
        valid_unique.append({
            "name": name,
            "domain": dom,
            "sector": sec,
            "primary_hub": hub
        })
        prior_names.add(nl)
    else:
        print(f"Already in prior: {name}")

print(f"Found {len(valid_unique)} valid unique new companies from candidate pool.")


if len(valid_unique) >= 50:
    out_file = os.path.join(scripts_dir, "prepare_batch22_company_list.py")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write('"""Curated Batch 22 Indian Industrial Manufacturing Companies (Guaranteed Zero Overlap with Batches 1-21).\n')
        f.write('Prepared specifically for Upstream Trigger Quality Recovery Validation (Phase 11).\n"""\n')
        f.write("from typing import Dict, List\n\n")
        f.write("BATCH_22_COMPANIES: List[Dict[str, str]] = [\n")
        for c in valid_unique[:50]:
            f.write("    {\n")
            f.write(f'        "name": "{c["name"]}",\n')
            f.write(f'        "domain": "{c["domain"]}",\n')
            f.write(f'        "sector": "{c["sector"]}",\n')
            f.write(f'        "primary_hub": "{c["primary_hub"]}",\n')
            f.write("    },\n")
        f.write("]\n")
    print(f"Generated {out_file} with exactly 50 brand new companies!")
