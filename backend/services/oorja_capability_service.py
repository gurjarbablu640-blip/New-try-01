"""Oorja Technical Services Capability & NABL Scope Source of Truth.

Accreditation Details:
- Laboratory: Oorja Technical Services Calibration Laboratory
- Certificate Number: CC-3963
- Standard: ISO/IEC 17025:2017
- Source Document: Oorja NABL Scope-Calibration.pdf
- Data Provenance: USER_PROVIDED_REAL_DATA
- Status: Active ISO 17025 Accredited Calibration Laboratory
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping, Optional, Sequence

OORJA_OFFICIAL_CERTIFICATE_NO = "CC-3963"
OORJA_ACCREDITATION_STANDARD = "ISO/IEC 17025:2017"
OORJA_SOURCE_DOCUMENT = "Oorja NABL Scope-Calibration.pdf"
OORJA_LAST_VERIFIED_DATE = "2026-09-10"

# Strict classification outcomes
CONFIRMED_NABL_SCOPE = "CONFIRMED_NABL_SCOPE"
KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED = "KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED"
POSSIBLE = "POSSIBLE"
UNKNOWN = "UNKNOWN"
OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True)
class OorjaCapabilityEntry:
    discipline: str
    parameter_name: str
    instrument_or_gage: str
    range_description: str
    cmc_uncertainty: str
    service_capability: str  # LAB_ONLY, ONSITE_ONLY, LAB_AND_ONSITE
    is_nabl_accredited: bool
    evidence_source: str
    certificate_no: str
    last_verified_date: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Verified NABL schedule entries extracted directly from CC-3963 source document
VERIFIED_CC3963_SCHEDULE: list[OorjaCapabilityEntry] = [
    # Mechanical & Dimensional
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Coordinate Measuring Machine (CMM)",
        instrument_or_gage="CMM / 3D CMM / Bridge CMM",
        range_description="0 to 1200 mm",
        cmc_uncertainty="±(2.5 + 3L/1000) µm",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Caliper & Depth Gauges",
        instrument_or_gage="Vernier Caliper, Digital Caliper, Dial Caliper, Depth Caliper",
        range_description="0 to 600 mm",
        cmc_uncertainty="±12.0 µm",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Micrometers",
        instrument_or_gage="External Micrometer, Internal Micrometer, Depth Micrometer",
        range_description="0 to 300 mm",
        cmc_uncertainty="±2.5 µm",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Dial Gauges & Indicators",
        instrument_or_gage="Dial Indicator, Plunger Gauge, Lever Dial Indicator, Bore Gauge",
        range_description="0 to 50 mm",
        cmc_uncertainty="±1.8 µm",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Height Gauges & Height Masters",
        instrument_or_gage="Electronic Height Gauge, Vernier Height Gauge, Height Master",
        range_description="0 to 600 mm",
        cmc_uncertainty="±3.0 µm",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Gauge Blocks & Standards",
        instrument_or_gage="Gauge Block, Slip Gauge, Length Bar, Pin Gauge, Snap Gauge, Thread Gauge",
        range_description="0.5 mm to 100 mm",
        cmc_uncertainty="±0.15 µm",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Surface Plates & Flatness",
        instrument_or_gage="Granite Surface Plate, Cast Iron Surface Plate",
        range_description="Up to 2000 mm x 1000 mm",
        cmc_uncertainty="±3.5 µm",
        service_capability="ONSITE_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Torque Measuring Instruments",
        instrument_or_gage="Torque Wrench, Torque Transducer, Torque Screwdriver",
        range_description="5 Nm to 1000 Nm",
        cmc_uncertainty="±1.0% to ±1.5%",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Pressure & Vacuum Gauges",
        instrument_or_gage="Bourdon Tube Pressure Gauge, Vacuum Gauge, Digital Pressure Gauge, Pressure Transmitter, DP Transmitter",
        range_description="-0.95 bar to 700 bar",
        cmc_uncertainty="±0.05% to ±0.25% FS",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Mechanical",
        parameter_name="Weighing Instruments & Mass",
        instrument_or_gage="Analytical Balance, Precision Balance, Standard Weights (Class F1/M1)",
        range_description="1 mg to 200 kg",
        cmc_uncertainty="±0.1 mg to ±50 mg",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    # Thermal
    OorjaCapabilityEntry(
        discipline="Thermal",
        parameter_name="RTD & Temperature Sensors",
        instrument_or_gage="RTD Pt100, Temperature Indicator, Temperature Datalogger",
        range_description="-50°C to 600°C",
        cmc_uncertainty="±0.35°C",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Thermal",
        parameter_name="Thermocouples",
        instrument_or_gage="Thermocouple Type J, K, R, S, T, Temperature Bath",
        range_description="0°C to 1200°C",
        cmc_uncertainty="±1.2°C",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Thermal",
        parameter_name="Environmental & Thermal Chambers",
        instrument_or_gage="Environmental Chamber, Muffle Furnace, Hot Air Oven, Incubator",
        range_description="-40°C to 250°C",
        cmc_uncertainty="±0.8°C",
        service_capability="ONSITE_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    # Electro-Technical
    OorjaCapabilityEntry(
        discipline="Electro-Technical",
        parameter_name="Multimeters & Electrical Meters",
        instrument_or_gage="Digital Multimeter (up to 6.5 digit), Voltmeter, Ammeter, Clamp Meter",
        range_description="1 mV to 1000 V, 10 µA to 10 A, 1 Ω to 100 MΩ",
        cmc_uncertainty="±0.005% to ±0.1%",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    OorjaCapabilityEntry(
        discipline="Electro-Technical",
        parameter_name="Process Calibrators & Sources",
        instrument_or_gage="Loop Calibrator, Process Calibrator, Decade Resistance Box",
        range_description="0 to 24 mA, 0 to 10 V",
        cmc_uncertainty="±0.02%",
        service_capability="LAB_AND_ONSITE",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
    # Optical
    OorjaCapabilityEntry(
        discipline="Optical",
        parameter_name="Optical Flats & Gauges",
        instrument_or_gage="Optical Flat, Monochromatic Light Source",
        range_description="0 to 150 mm",
        cmc_uncertainty="±0.05 µm",
        service_capability="LAB_ONLY",
        is_nabl_accredited=True,
        evidence_source=OORJA_SOURCE_DOCUMENT,
        certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO,
        last_verified_date=OORJA_LAST_VERIFIED_DATE,
    ),
]

# Explicitly verified non-scope services offered by Oorja outside direct NABL certificate
KNOWN_OORJA_NON_SCOPE_SERVICES = {
    "non-nabl factory calibration",
    "factory calibration",
    "visual inspection",
    "instrument maintenance",
    "master list asset audit",
    "preventive maintenance",
    "calibration management consulting",
}

# Explicitly unsupported services (MUST NOT be claimed or offered as Oorja NABL capability)
OUT_OF_SCOPE_SERVICES = {
    "metallurgical testing",
    "metallurgical",
    "optical emission spectrometer",
    "spectrometer",
    "xrf",
    "x-ray fluorescence",
    "ultrasonic flaw detector",
    "flaw detector",
    "tensile destruction testing",
    "destructive testing",
    "chemical assay",
    "chromatography",
    "gas chromatography",
    "hplc testing",
    "gc-ms",
    "radiation meter",
    "radiography",
    "hardness destructive test",
}


def _match_verified_entry(clean_text: str) -> Optional[OorjaCapabilityEntry]:
    """Match clean instrument string against verified CC-3963 schedule."""
    # Pattern matching against verified schedule entries
    checks = [
        ("cmm", "Coordinate Measuring Machine (CMM)"),
        ("coordinate measuring", "Coordinate Measuring Machine (CMM)"),
        ("caliper", "Caliper & Depth Gauges"),
        ("vernier", "Caliper & Depth Gauges"),
        ("micrometer", "Micrometers"),
        ("dial indicator", "Dial Gauges & Indicators"),
        ("dial gauge", "Dial Gauges & Indicators"),
        ("plunger gauge", "Dial Gauges & Indicators"),
        ("bore gauge", "Dial Gauges & Indicators"),
        ("height gauge", "Height Gauges & Height Masters"),
        ("height master", "Height Gauges & Height Masters"),
        ("gauge block", "Gauge Blocks & Standards"),
        ("slip gauge", "Gauge Blocks & Standards"),
        ("pin gauge", "Gauge Blocks & Standards"),
        ("snap gauge", "Gauge Blocks & Standards"),
        ("thread gauge", "Gauge Blocks & Standards"),
        ("surface plate", "Surface Plates & Flatness"),
        ("optical flat", "Optical Flats & Gauges"),
        ("torque wrench", "Torque Measuring Instruments"),
        ("torque transducer", "Torque Measuring Instruments"),
        ("pressure gauge", "Pressure & Vacuum Gauges"),
        ("vacuum gauge", "Pressure & Vacuum Gauges"),
        ("pressure transmitter", "Pressure & Vacuum Gauges"),
        ("dp transmitter", "Pressure & Vacuum Gauges"),
        ("dead weight tester", "Pressure & Vacuum Gauges"),
        ("analytical balance", "Weighing Instruments & Mass"),
        ("precision balance", "Weighing Instruments & Mass"),
        ("standard weight", "Weighing Instruments & Mass"),
        ("weighing scale", "Weighing Instruments & Mass"),
        ("rtd", "RTD & Temperature Sensors"),
        ("pt100", "RTD & Temperature Sensors"),
        ("temperature sensor", "RTD & Temperature Sensors"),
        ("temperature datalogger", "RTD & Temperature Sensors"),
        ("thermocouple", "Thermocouples"),
        ("environmental chamber", "Environmental & Thermal Chambers"),
        ("test chamber", "Environmental & Thermal Chambers"),
        ("muffle furnace", "Environmental & Thermal Chambers"),
        ("hot air oven", "Environmental & Thermal Chambers"),
        ("incubator", "Environmental & Thermal Chambers"),
        ("multimeter", "Multimeters & Electrical Meters"),
        ("digital multimeter", "Multimeters & Electrical Meters"),
        ("clamp meter", "Multimeters & Electrical Meters"),
        ("voltmeter", "Multimeters & Electrical Meters"),
        ("ammeter", "Multimeters & Electrical Meters"),
        ("process calibrator", "Process Calibrators & Sources"),
        ("loop calibrator", "Process Calibrators & Sources"),
        ("decade resistance", "Process Calibrators & Sources"),
    ]

    for kw, param_title in checks:
        if kw in clean_text:
            for entry in VERIFIED_CC3963_SCHEDULE:
                if entry.parameter_name == param_title:
                    return entry

    return None


def classify_capability(
    instrument_or_service: str,
    certificate_no: Optional[str] = None,
    db: Optional[Any] = None,
) -> dict[str, Any]:
    """Strictly classify instrument or service against Oorja CC-3963 NABL scope.

    Rules:
    1. If an unknown certificate number is specified (!= CC-3963), CANNOT be CONFIRMED_NABL_SCOPE.
    2. Checked against OUT_OF_SCOPE_SERVICES -> OUT_OF_SCOPE.
    3. Checked against verified CC-3963 schedule -> CONFIRMED_NABL_SCOPE.
    4. Checked against known non-scope services -> KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED.
    5. Plausible measurement/sensors without verified entry -> POSSIBLE.
    6. All other -> UNKNOWN.
    """
    raw_str = str(instrument_or_service or "").strip()
    clean = raw_str.lower()

    if not clean:
        return {
            "item": raw_str,
            "classification": UNKNOWN,
            "reason": "Empty or unspecified instrument/service query",
            "entry": None,
        }

    # Rule A: Certificate number validation
    if certificate_no and str(certificate_no).strip().upper() != OORJA_OFFICIAL_CERTIFICATE_NO:
        return {
            "item": raw_str,
            "classification": UNKNOWN,
            "reason": f"Certificate number '{certificate_no}' is not the verified Oorja NABL certificate ({OORJA_OFFICIAL_CERTIFICATE_NO})",
            "entry": None,
        }

    # Rule B: Out of scope check
    if any(oos in clean for oos in OUT_OF_SCOPE_SERVICES):
        return {
            "item": raw_str,
            "classification": OUT_OF_SCOPE,
            "reason": "Service/instrument is outside Oorja calibration scope (destructive testing, metallurgical testing, or chemical spectrometry)",
            "entry": None,
        }

    # Rule C: Match against verified CC-3963 schedule
    entry = _match_verified_entry(clean)
    if entry is not None:
        return {
            "item": raw_str,
            "classification": CONFIRMED_NABL_SCOPE,
            "reason": f"Verified under Oorja NABL schedule ({entry.certificate_no}, {entry.discipline})",
            "entry": entry.to_dict(),
        }

    # Rule D: Known non-scope verified services
    if any(s in clean for s in KNOWN_OORJA_NON_SCOPE_SERVICES):
        return {
            "item": raw_str,
            "classification": KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED,
            "reason": "Recognized Oorja technical service, but not covered by official CC-3963 NABL scope schedule",
            "entry": None,
        }

    # Rule E: Plausible generic calibration keywords without source evidence
    plausible_keywords = [
        "gauge", "meter", "sensor", "transmitter", "calibrat", "indicator",
        "flow", "lux", "sound", "anemometer", "tachometer", "pyrometer", "vibration",
    ]
    if any(pk in clean for pk in plausible_keywords):
        return {
            "item": raw_str,
            "classification": POSSIBLE,
            "reason": "Generic plausible measurement instrument; not confirmed in stored CC-3963 NABL schedule",
            "entry": None,
        }

    return {
        "item": raw_str,
        "classification": UNKNOWN,
        "reason": "Unrecognized instrument or service; no Oorja capability evidence found",
        "entry": None,
    }


def classify_technical_scope_batch(
    scope_items: Sequence[str],
    certificate_no: Optional[str] = OORJA_OFFICIAL_CERTIFICATE_NO,
    db: Optional[Any] = None,
) -> dict[str, Any]:
    """Classify a list of requested instruments into the 5 strict tiers."""
    confirmed: list[dict[str, Any]] = []
    known_non_scope: list[str] = []
    possible: list[str] = []
    unknown: list[str] = []
    out_of_scope: list[str] = []

    for item in scope_items:
        res = classify_capability(item, certificate_no=certificate_no, db=db)
        cls = res["classification"]
        if cls == CONFIRMED_NABL_SCOPE:
            confirmed.append({"item": item, "details": res["entry"]})
        elif cls == KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED:
            known_non_scope.append(item)
        elif cls == POSSIBLE:
            possible.append(item)
        elif cls == OUT_OF_SCOPE:
            out_of_scope.append(item)
        else:
            unknown.append(item)

    return {
        "certificate_no": certificate_no or OORJA_OFFICIAL_CERTIFICATE_NO,
        "CONFIRMED_NABL_SCOPE": confirmed,
        "KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED": known_non_scope,
        "POSSIBLE": possible,
        "UNKNOWN": unknown,
        "OUT_OF_SCOPE": out_of_scope,
    }
