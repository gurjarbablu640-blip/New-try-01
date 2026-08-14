"""Deterministic quotation intelligence services.

The service layer intentionally keeps pricing recommendations explainable and
human-controlled. It normalizes common instrument aliases, records historical
prices, and finds comparable historical quote items.
"""
import re
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.sales_os import Instrument, InstrumentAlias, PriceHistory, QuotationItem


DEFAULT_ALIASES = {
    "temperature indicator": "Temperature Indicator",
    "temp indicator": "Temperature Indicator",
    "temp. indicator": "Temperature Indicator",
    "temperature display": "Temperature Indicator",
    "digital thermometer": "Digital Thermometer",
    "temp sensor": "Temperature Sensor",
    "temperature sensor": "Temperature Sensor",
    "pressure gauge": "Pressure Gauge",
    "pressure transmitter": "Pressure Transmitter",
    "digital multimeter": "Digital Multimeter",
    "dmm": "Digital Multimeter",
    "clamp meter": "Clamp Meter",
    "power analyzer": "Power Analyzer",
    "energy meter": "Energy Meter",
    "megger": "Insulation Resistance Tester",
}


def normalize_instrument_name(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    text = re.sub(r"[._/-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return DEFAULT_ALIASES.get(text, text.title())


def resolve_instrument(db: Session, raw_name: str) -> tuple[Optional[Instrument], str, float]:
    normalized = normalize_instrument_name(raw_name)
    direct = db.query(Instrument).filter(func.lower(Instrument.family) == normalized.lower()).first()
    if direct:
        return direct, normalized, 100.0

    alias = (
        db.query(InstrumentAlias)
        .filter(func.lower(InstrumentAlias.alias) == (raw_name or "").strip().lower())
        .first()
    )
    if alias:
        instrument = db.query(Instrument).filter(Instrument.id == alias.instrument_id).first()
        if instrument:
            return instrument, instrument.family, float(alias.confidence or 0)

    return None, normalized, 0.0


def ensure_instrument(db: Session, raw_name: str, parameter: str | None = None) -> tuple[Instrument, str, float]:
    existing, normalized, confidence = resolve_instrument(db, raw_name)
    if existing:
        return existing, normalized, confidence

    instrument = Instrument(family=normalized, parameter=parameter, nabl_applicable=None)
    db.add(instrument)
    db.flush()
    if raw_name and raw_name.strip().lower() != normalized.lower():
        db.add(
            InstrumentAlias(
                instrument_id=instrument.id,
                alias=raw_name.strip(),
                source="normalizer",
                confidence=90,
            )
        )
    return instrument, normalized, 90.0


def similar_quote_items(
    db: Session,
    instrument_name: str,
    make: str | None = None,
    parameter: str | None = None,
    calibration_type: str | None = None,
    location: str | None = None,
    limit: int = 20,
) -> list[dict]:
    _, normalized, confidence = resolve_instrument(db, instrument_name)
    query = (
        db.query(QuotationItem, PriceHistory)
        .outerjoin(PriceHistory, PriceHistory.quotation_id == QuotationItem.quotation_id)
        .filter(func.lower(QuotationItem.normalized_name) == normalized.lower())
    )
    if make:
        query = query.filter(func.lower(QuotationItem.make) == make.lower())
    if parameter:
        query = query.filter(func.lower(QuotationItem.parameter) == parameter.lower())
    if limit:
        query = query.limit(min(max(limit, 1), 100))

    results = []
    for item, price in query.all():
        results.append(
            {
                "quotation_item_id": item.id,
                "quotation_id": item.quotation_id,
                "instrument_name": item.instrument_name,
                "normalized_name": item.normalized_name,
                "make": item.make,
                "model": item.model,
                "parameter": item.parameter,
                "range_value": item.range_value,
                "quantity": float(item.quantity or 0),
                "unit_price": float(item.unit_price or 0),
                "price_source": item.price_source,
                "quotation_date": price.quotation_date if price else None,
                "calibration_type": price.calibration_type if price else calibration_type,
                "location": price.location if price else location,
                "outcome": price.outcome if price else None,
                "match_confidence": confidence,
            }
        )
    return results


def price_recommendation(
    db: Session,
    instrument_name: str,
    make: str | None = None,
    parameter: str | None = None,
    calibration_type: str | None = None,
    location: str | None = None,
    limit: int = 20,
) -> dict:
    matches = similar_quote_items(
        db,
        instrument_name,
        make=make,
        parameter=parameter,
        calibration_type=calibration_type,
        location=location,
        limit=limit,
    )
    prices = [Decimal(str(row["unit_price"])) for row in matches if row["unit_price"] is not None and row["unit_price"] > 0]
    if not prices:
        return {
            "recommended_unit_price": None,
            "currency": "INR",
            "basis": "No historical price found",
            "confidence": 0,
            "matches": matches,
            "human_approval_required": True,
        }

    prices_sorted = sorted(prices)
    midpoint = prices_sorted[len(prices_sorted) // 2]
    confidence = min(95, 45 + len(prices_sorted) * 5)
    return {
        "recommended_unit_price": float(midpoint),
        "currency": "INR",
        "basis": "historical_median",
        "sample_size": len(prices_sorted),
        "min_historical_price": float(min(prices_sorted)),
        "max_historical_price": float(max(prices_sorted)),
        "confidence": confidence,
        "matches": matches,
        "human_approval_required": True,
    }


def record_price_history(
    db: Session,
    quotation_id: int,
    customer_name: str,
    instrument_id: int | None,
    calibration_type: str | None,
    location: str | None,
    unit_price: Decimal,
    quotation_date,
    outcome: str | None = None,
    context: dict | None = None,
) -> PriceHistory:
    record = PriceHistory(
        quotation_id=quotation_id,
        customer_name=customer_name,
        instrument_id=instrument_id,
        calibration_type=calibration_type,
        location=location,
        unit_price=unit_price,
        quotation_date=quotation_date,
        outcome=outcome,
        context=context,
    )
    db.add(record)
    return record
