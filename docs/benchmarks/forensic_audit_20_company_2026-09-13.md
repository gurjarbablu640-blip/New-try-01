# SALESOORJA — FORENSIC AUDIT OF 20-COMPANY BENCHMARK

**Audit Date:** September 13, 2026  
**Artifact Audited:** `backend/data/runtime_state/blind_20_benchmark_results.json`  
**Telemetry & Search Cache Audited:** `backend/data/runtime_state/search_provider_cache.json` & `backend/data/runtime_state/serper_budget_state.json`  
**Benchmark Classification:** `SEMI_BLIND_PIPELINE_BENCHMARK` (Facility preseeded: YES)

---

## 1. EXECUTIVE SUMMARY & KEY FINDINGS

1. **Benchmark Classification**:
   - The benchmark preseeded `target_facility`, `city`, and `state` in `TARGET_20_COMPANIES`.
   - Therefore, this run tested **pipeline qualification and facility validation**, **NOT autonomous facility discovery**.
   - `FACILITY_DISCOVERY_READY = NOT TESTED`.

2. **Trigger Truth**:
   - Only **4 / 20** triggers are **VERIFIED** commercial manufacturing events (`Amara Raja`, `Divi's`, `Waaree`, `Dixon`).
   - **3 / 20** triggers are **PARTIALLY_VERIFIED** (`Ola Electric`, `Thermax`, `TASL`).
   - **13 / 20** triggers are **WEAK / INVALID** (static plant profiles, directory listings, CSR posts, or 10-year-old stale case study PDFs) that were forced into `CAPACITY_EXPANSION` with default fallback dates `2025-2026`.

3. **Facility Validation**:
   - Direct/Strong facility confirmation occurred for **19 / 20** companies because the plant name and city were preseeded.
   - However, linking the trigger to the target facility succeeded in only **7 / 20** records. In 12 cases, the search engine merely confirmed that the company operates a plant in that city without proving any expansion.

4. **Person Truth (The 15 Claimed "READY" Leads)**:
   - Only **6 / 15** claimed ready people were verified for the target facility.
   - **2 / 15** are group/corporate-level quality executives.
   - **7 / 15** are unverified, past employees, or located at different facilities in different states.
   - **3 Serious False-Ready Cases passed into READY**:
     - `Schneider Electric / Himanshu Sharma`: Left Schneider 17 years ago in Nov 2009; currently AVP Quality at Crompton.
     - `Tata Motors / Avijit Sen`: Head of Plant QA at Dharwad, Karnataka, NOT Sanand, Gujarat.
     - `RR Kabel / Praveen Kumar`: Plant Quality Head at Baddi, Himachal Pradesh, NOT Waghodia, Gujarat.

5. **Serper Budget Discrepancy**:
   - `BENCHMARK_SERPER_LIMIT = 150`
   - `ACTUAL_LIVE_REQUESTS = 164`
   - `LIMIT_ENFORCED = NO` (Checked only at coarse company boundary, not query level; rerun added uncached calls for Companies 19 & 20).

6. **Calibration Specificity**:
   - `SOURCE_SUPPORTED = 0 / 20` (0%): Not a single specific instrument (CMM, laser micrometer, spark tester, HPLC flow meter) was mentioned in source evidence.
   - `REASONABLE_INFERENCE = 20 / 20` (100%): Inferred standard equipment based on manufacturing sector.
   - `UNSUPPORTED_SPECIFICITY = 20 / 20` (100%): Presenting hardcoded equipment lists as discovered customer requirements is unsupported.

7. **Score Distribution**:
   - Severe artificial score compression: `P1 = 0`, `P2 = 15`, `P3 = 0`, `HOLD = 5`.
   - Scores clustered rigidly at 90.0, 92.0, and 94.0 due to an additive formula (`85 base + 5 CURRENT + 0 STRONG facility + 4/2/0 person score`).

8. **Production Readiness**:
   - `TRIGGER_DISCOVERY_READY: PARTIAL`
   - `FACILITY_DISCOVERY_READY: NOT TESTED`
   - `FACILITY_VALIDATION_READY: PARTIAL`
   - `PERSON_DISCOVERY_READY: PARTIAL`
   - `PERSON_VERIFICATION_READY: PARTIAL`
   - `SERPER_PRODUCTION_ROUTER_READY: YES`
   - `READY_FOR_APOLLO_PILOT: NO`
   - `READY_FOR_150_DAILY_PRODUCTION: NO`

---

## 2. AUDIT 1 — SERPER BUDGET DISCREPANCY

```
BENCHMARK_SERPER_LIMIT = 150
ACTUAL_LIVE_REQUESTS = 164
LIMIT_ENFORCED = NO
ROOT_CAUSE = Coarse loop boundary check + Multi-pass rerun accumulation
```

### Analysis
In `backend/scripts/run_blind_20_benchmark.py`:
- `BENCHMARK_MAX_LIVE_SERPER_REQUESTS = 150` was defined at line 72.
- The enforcement check at line 570 evaluated `current_live_used >= 150` strictly at the company loop boundary before starting a company.
- At Company 18 (`RR Kabel`), `current_live_used` was 146 (< 150). The script allowed Company 18 to proceed, which executed 6 queries, pushing live usage to 152.
- At Company 19 (`Dynamatic Technologies`), `current_live_used` was 152 >= 150, causing the benchmark to break early.
- When the benchmark was subsequently executed to complete the 20 companies:
  - Companies 1–18 hit the cache (0 live requests).
  - Companies 19 and 20 ran live: 6 queries each = 12 live requests.
  - Cumulative live requests across sessions = 152 + 12 = 164 live requests.

---

## 3. AUDIT 2 — TRIGGER TRUTH (ALL 20 RECORDS)

```
TRIGGERS VERIFIED: 4 / 20 (20.0%)
TRIGGERS PARTIALLY VERIFIED: 3 / 20 (15.0%)
TRIGGERS WEAK / INVALID: 13 / 20 (65.0%)
```

| # | Company | Target Facility | Recorded Type | True Event Type | Exact Event / Pub Date | Source URL | Facility Linkage | Reality & Calibration Need | Classification |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Tata Motors Limited | Sanand | CAPACITY_EXPANSION | STATIC_CORPORATE_PAGE | None (Static) | `tatamotors.com/media-libraries/sanand/` | DIRECT | Corporate media library; no expansion event. | WEAK |
| 2 | Uno Minda Limited | Bawal | CAPACITY_EXPANSION | STATIC_JV_PROFILE | None (Static) | `unominda.com/.../roki-uno-minda` | STRONG | Static joint venture profile; routine ops. | WEAK |
| 3 | Amara Raja Energy & Mobility | Divitipally / Mahbubnagar | CAPACITY_EXPANSION | NEW_PLANT / COMMISSIONING | July 2024 | `amararaja.com/press_release/...` | DIRECT | Genuine battery pack assembly plant & customer qualification plant. | VERIFIED |
| 4 | Ola Electric Mobility | Futurefactory Pochampalli | CAPACITY_EXPANSION | QUALITY_VALIDATION | August 2024 | `economictimes.indiatimes.com/.../112660038` | STRONG | ARAI PLI certification milestone. | PARTIALLY_VERIFIED |
| 5 | Schneider Electric India | GMR Industrial Park, Hyderabad | CAPACITY_EXPANSION | DIRECTORY_LISTING | 2017 (GST Date) | `indiamart.com/.../aboutus.html` | STRONG | IndiaMART listing with GST date 2017; zero capex trigger. | INVALID |
| 6 | Havells India Limited | Ghiloth Plant, Alwar | CAPACITY_EXPANSION | ARCHITECTURAL_PORTFOLIO | None (Undated) | `cpkukreja.com/.../havells-india-limited.html` | STRONG | Architectural case study of existing plant. | WEAK |
| 7 | Kaynes Technology India | Kongara Kalan, Hyderabad | CAPACITY_EXPANSION | CSR_EVENT | 2024 | `linkedin.com/company/kaynes-technology` | STRONG | LinkedIn post about tree planting and blood donation CSR drive. | INVALID |
| 8 | Dixon Technologies (India) | Oragadam Plant | CAPACITY_EXPANSION | PRODUCTION_RAMP / HIRING | April 2024 | `linkedin.com/posts/dixoninfo_walk-in-interview...` | DIRECT | Walk-in hiring drive for Oragadam III facility. | VERIFIED |
| 9 | Deepak Nitrite Limited | Dahej Plant | CAPACITY_EXPANSION | STATIC_CONTACT_PAGE | None (Static) | `godeepak.com/contact-us/` | DIRECT | Corporate contact us address listing. | INVALID |
| 10 | Divi's Laboratories Limited | Unit-III Ontimamidi, Kakinada | CAPACITY_EXPANSION | COMMISSIONING / NEW_PLANT | January 2025 | `divislabs.com/.../world-largest-api-manufacturing-facility/` | DIRECT | Commenced operations at Kakinada Unit-III in Jan 2025. | VERIFIED |
| 11 | Premier Energies Limited | Raviryala / E-City | CAPACITY_EXPANSION | CORPORATE_OFFICE_PAGE | None (Static) | `premierenergies.com/about-premier-energies` | AMBIGUOUS | Corporate office in Raidurgam, not manufacturing unit in Raviryala. | INVALID |
| 12 | Waaree Energies Limited | Chikhli Plant, Navsari | CAPACITY_EXPANSION | QUALITY_VALIDATION / RAMP | 16 Dec 2025 | `waaree.com/press-release/waaree-reinforces...` | DIRECT | MNRE ALMM List-II enlistment for 5.25GW Chikhli solar cells. | VERIFIED |
| 13 | Ace Designers Limited | Peenya Plant, Bengaluru | CAPACITY_EXPANSION | GENERIC_COMPANY_BIO | None (Static) | `linkedin.com/company/acedesigners` | STRONG | LinkedIn company profile; routine ops. | INVALID |
| 14 | Jyoti CNC Automation Limited | Metoda GIDC, Rajkot | CAPACITY_EXPANSION | STATIC_PROFILE_PAGE | None (Static) | `jyoti.co.in/about-us/company-profile/` | STRONG | Company profile describing Rajkot plant shops; routine ops. | WEAK |
| 15 | Thermax Limited | Sri City Plant | CAPACITY_EXPANSION | QUALITY_VALIDATION | 2024 | `facebook.com/Thermaxglobal/...` | DIRECT | CII Platinum green certification award. | PARTIALLY_VERIFIED |
| 16 | Kirloskar Oil Engines Limited | Kagal MIDC, Kolhapur | CAPACITY_EXPANSION | STALE_CASE_STUDY | 2016 (10 years stale!) | `greenco.in/.../GreenCo%20Journey...Kagal-2016.pdf` | STRONG | GreenCo case study PDF from 2016; 10 years old. | INVALID |
| 17 | Polycab India Limited | Halol Plant | CAPACITY_EXPANSION | STATIC_FACILITY_DIRECTORY | None (Static) | `polycab.com/industries/manufacturing-facilities` | DIRECT | Corporate facilities page; routine cable manufacturing. | WEAK |
| 18 | RR Kabel Limited | Waghodia Plant, Vadodara | CAPACITY_EXPANSION | STATIC_FACILITY_DIRECTORY | None (Static) | `rrkabel.com/factories/` | DIRECT | Corporate factories page; routine wire manufacturing. | WEAK |
| 19 | Dynamatic Technologies | Devanahalli, Bengaluru | CAPACITY_EXPANSION | GENERIC_COMPANY_BIO | None (Static) | `linkedin.com/company/dynamatic-technologies-limited` | STRONG | LinkedIn company overview; routine aerospace machining. | INVALID |
| 20 | Tata Advanced Systems Limited | Adibatla Aerospace SEZ | CAPACITY_EXPANSION | PRODUCTION_RAMP / HIRING | Recent 2025/2026 | `linkedin.com/company/tataadvanced` | STRONG | Recruitment drive for Hyderabad assembly operators. | PARTIALLY_VERIFIED |

---

## 4. AUDIT 3 — FACILITY VALIDATION

- **Preseeded Facility Validation**: 19 / 20 confirmed plant presence (`DIRECT` = 7, `STRONG` = 12, `AMBIGUOUS` = 1).
- **Trigger Tied to Target Facility**: Only **7 / 20** events actually tied directly to operations at that plant.
- In 12 cases, the trigger search fell back to queries that confirmed the presence of a factory in the city, but discovered zero capex or expansion.

---

## 5. AUDIT 4 — PERSON TRUTH (THE 15 CLAIMED "READY" LEADS)

```
PEOPLE VERIFIED FOR TARGET FACILITY: 6 / 15 (40.0%)
PEOPLE ONLY GROUP / CORPORATE LEVEL: 2 / 15 (13.3%)
PEOPLE UNVERIFIED / CONTRADICTED: 7 / 15 (46.7%)
```

### Categorization of 15 Evaluated Leads

#### Category A: Verified for Target Facility (6 Leads)
1. **Polycab India Limited — Kuldeep Singh**: Chief Manager Quality Assurance (Plant). Verified present at Halol, Gujarat. Direct plant QA owner.
2. **Divi's Laboratories Limited — Ravi Kumar Meka**: Head of Quality (AVP). Verified present at Divi's API manufacturing site. Direct plant QA head.
3. **Tata Advanced Systems Limited — Saurabh Gupta**: Quality Head. Verified present at Hyderabad aerospace manufacturing facility. Direct plant QA head.
4. **Kirloskar Oil Engines Limited — Pravin Amate**: Quality Assurance Manager. Verified present in Kolhapur (Kagal plant site). Direct plant QA manager.
5. **Premier Energies Limited — Kapil Sharma**: Quality Manager. Verified present in Hyderabad manufacturing cluster. Direct plant QA manager.
6. **Ace Designers Limited — Nanda UL**: Plant Quality Assurance Lead. Verified present at Peenya machinery manufacturing plant (18 years tenure). Direct plant QA lead.

#### Category B: Group / Corporate Level (2 Leads)
7. **Havells India Limited — Keshava Babu C S**: Vice President & Group Quality Head. Located at Noida Corporate HQ. Oversees corporate quality policy, but not local Ghiloth plant QA manager.
8. **Dixon Technologies (India) — Anil Razdan**: Quality Head. Located at Noida facility/HQ. Does not head Oragadam (Tamil Nadu) plant quality directly.

#### Category C: Contradicted / False Positives (3 Leads)
9. **Schneider Electric India — Himanshu Sharma**: CONTRADICTED. Left Schneider Electric in November 2009 (17 years ago). Currently AVP Quality at Crompton Greaves. Passed as READY with score 90.0.
10. **Tata Motors Limited — Avijit Sen**: CONTRADICTED FACILITY. Profile explicitly states Head of Plant QA at **Dharwad, Karnataka**, NOT Sanand, Gujarat. Passed as READY with score 92.0.
11. **RR Kabel Limited — Praveen Kumar**: CONTRADICTED FACILITY. Profile explicitly states Plant Quality Head at **Baddi, Himachal Pradesh**, NOT Waghodia, Gujarat. Passed as READY with score 92.0.

#### Category D: Unverified Location / Junior / Currency (4 Leads)
12. **Uno Minda Limited — Sashikanta Sahoo**: Plant Quality Head for Mirror division. Plant location omitted from snippet (division has plants in Bawal, Bengaluru, Pune).
13. **Kaynes Technology India — Amit Yadav**: Junior QA Engineer. College in Ghaziabad, location omitted; lacks vendor/calibration authority.
14. **Thermax Limited — Nitin Adya**: Head Quality Assurance. Snippet highlights past role at Elecon Engg; current Thermax role dates and plant location unverified.
15. **Dynamatic Technologies — Lokesh hv**: Quality Assurance Manager. ZoomInfo snippet explicitly says *"Previously managed plant quality"*; employment currency unverified.

---

## 6. AUDIT 5 — CALIBRATION ANGLE SPECIFICITY

- **Source Supported (0 / 20)**: Zero equipment mentions came from source evidence.
- **Reasonable Inference (20 / 20)**: Equipment types reflect genuine requirements of these manufacturing sectors.
- **Unsupported Specificity (20 / 20)**: Generated by hardcoded `CALIBRATION_SECTOR_MAP` in Python. Must be framed in outreach as typical sector equipment, never as customer-specific findings.

---

## 7. AUDIT 6 — SCORE DISTRIBUTION & COMPRESSION

- Rigid additive benchmark scoring formula:
  `lead_score = 85.0 + 5.0 (CURRENT trigger) + 0.0 (STRONG facility) + [4.0 (HIGH conf) | 2.0 (score>=80) | 0.0 (<80)]`
- Compressed all 15 qualifying leads into exactly 90.0 (5 leads), 92.0 (6 leads), or 94.0 (4 leads).
- P1 (`>= 95.0`) was mathematically impossible (`max = 94.0`).
- P3 (`85.0 <= score < 90.0`) was mathematically impossible (`min = 90.0`).

---

## 8. AUDIT 8 — NON-HUMAN EXTRACTION FAILURES

Root causes for the 5 held candidates:
1. `Quality Head` (Amara Raja): Generic role phrase parsed as 2-word proper name from a snippet where the actual person was Surendranath Reddy.
2. `Propulsion Systems` (Ola Electric): Capitalized engineering subsystem parsed as proper name from Ajay Thanwal's post.
3. `Committee Composition. Designation` (Deepak Nitrite): Governance table header parsed as candidate name due to regex allowing period characters.
4. `Purchase Head` (Waaree Energies): Job listing text parsed as candidate name.
5. `CARBOGEN AMCIS Shanghai` (Jyoti CNC): Foreign CDMO subsidiary name parsed as proper name.

---

## 9. READINESS SCORECARD

```
TRIGGER_DISCOVERY_READY: PARTIAL
FACILITY_DISCOVERY_READY: NOT TESTED
FACILITY_VALIDATION_READY: PARTIAL
PERSON_DISCOVERY_READY: PARTIAL
PERSON_VERIFICATION_READY: PARTIAL
SERPER_PRODUCTION_ROUTER_READY: YES
READY_FOR_APOLLO_PILOT: NO
READY_FOR_150_DAILY_PRODUCTION: NO

NEXT BOTTLENECK:
1. Cross-checking person location vs plant city in deterministic scoring.
2. Filtering out past employment and stale dates from search snippets.
3. Upstream parser hygiene for generic roles, subsystems, and governance text.
```
