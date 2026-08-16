from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from database import SessionLocal
from models.knowledge import KnowledgeDocument, KnowledgeChunk

router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    document_type: str = "internal"
    company: Optional[str] = None
    source_uri: Optional[str] = None
    source_name: Optional[str] = None
    document_date: Optional[date] = None
    version: Optional[str] = None
    content_hash: Optional[str] = None
    metadata_json: Optional[dict] = None

class ChunkCreate(BaseModel):
    document_id: int
    chunk_index: int
    page_number: Optional[int] = None
    section: Optional[str] = None
    content: str = Field(min_length=1)
    fact_classification: str = "VERIFIED_FACT"
    source_reference: Optional[str] = None
    source_date: Optional[date] = None
    confidence: int = Field(default=100, ge=0, le=100)
    embedding_model: Optional[str] = None
    metadata_json: Optional[dict] = None

ALLOWED_CLASSIFICATIONS = {"VERIFIED_FACT", "AI_INFERENCE", "USER_CORRECTED_KNOWLEDGE"}

@router.post("/documents")
def create_document(payload: DocumentCreate):
    db = SessionLocal()
    try:
        if payload.content_hash:
            duplicate = db.query(KnowledgeDocument.id).filter(KnowledgeDocument.content_hash == payload.content_hash).first()
            if duplicate:
                raise HTTPException(409, "Document with this content hash already exists")
        item = KnowledgeDocument(**payload.model_dump())
        db.add(item); db.commit(); db.refresh(item)
        return {"id": item.id, "title": item.title, "status": item.status}
    finally:
        db.close()

@router.get("/documents")
def list_documents(document_type: Optional[str] = None, status: str = "active"):
    db = SessionLocal()
    try:
        q = db.query(KnowledgeDocument).filter(KnowledgeDocument.status == status)
        if document_type:
            q = q.filter(KnowledgeDocument.document_type == document_type)
        items = q.order_by(KnowledgeDocument.updated_at.desc()).all()
        return {"results": [{
            "id": x.id, "title": x.title, "document_type": x.document_type,
            "company": x.company, "source_name": x.source_name, "source_uri": x.source_uri,
            "document_date": x.document_date, "version": x.version,
            "status": x.status, "chunk_count": len(x.chunks)
        } for x in items], "total": len(items)}
    finally:
        db.close()

@router.post("/chunks")
def create_chunk(payload: ChunkCreate):
    if payload.fact_classification not in ALLOWED_CLASSIFICATIONS:
        raise HTTPException(400, "Unsupported fact classification")
    db = SessionLocal()
    try:
        doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == payload.document_id).first()
        if not doc:
            raise HTTPException(404, "Knowledge document not found")
        item = KnowledgeChunk(**payload.model_dump())
        item.source_reference = item.source_reference or doc.source_uri or doc.source_name
        item.source_date = item.source_date or doc.document_date
        db.add(item); db.commit(); db.refresh(item)
        return {"id": item.id, "document_id": item.document_id, "classification": item.fact_classification}
    finally:
        db.close()

@router.get("/search")
def search_knowledge(q: str, classification: Optional[str] = None, document_type: Optional[str] = None, limit: int = 20):
    db = SessionLocal()
    try:
        query = (
            db.query(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .filter(KnowledgeDocument.status == "active", KnowledgeChunk.content.ilike(f"%{q}%"))
        )
        if classification:
            query = query.filter(KnowledgeChunk.fact_classification == classification)
        if document_type:
            query = query.filter(KnowledgeDocument.document_type == document_type)
        rows = query.order_by(KnowledgeChunk.confidence.desc(), KnowledgeChunk.id.desc()).limit(min(max(limit, 1), 100)).all()
        return {"results": [{
            "chunk_id": c.id, "document_id": d.id, "title": d.title,
            "document_type": d.document_type, "company": d.company,
            "page_number": c.page_number, "section": c.section, "content": c.content,
            "classification": c.fact_classification, "confidence": c.confidence,
            "source_reference": c.source_reference or d.source_uri or d.source_name,
            "source_date": c.source_date or d.document_date,
            "version": d.version,
        } for c, d in rows], "total": len(rows), "query": q}
    finally:
        db.close()


@router.post("/seed-default-knowledge")
def seed_default_knowledge():
    """Seed foundational Oorja technical knowledge, NABL capabilities, SLAs, and commercial guidelines."""
    db = SessionLocal()
    try:
        # Check if already seeded
        existing = db.query(KnowledgeDocument).filter(KnowledgeDocument.title.like("Oorja Technical Services%")).first()
        if existing:
            return {"message": "Default Oorja knowledge is already seeded", "document_id": existing.id}

        # 1. NABL Scope Document
        doc_nabl = KnowledgeDocument(
            title="Oorja Technical Services — NABL Scope & Accreditation (CC-3498)",
            document_type="nabl_scope",
            company="Oorja Technical Services",
            source_name="NABL Scope Directory 2026",
            version="2026.1",
        )
        db.add(doc_nabl)
        db.flush()

        chunks = [
            KnowledgeChunk(
                document_id=doc_nabl.id,
                chunk_index=1,
                section="Pressure & Vacuum Scope",
                content="Pressure and Vacuum scope: Bourdon Tube Pressure Gauges, Vacuum Gauges, DP Transmitters, Pressure Switches, and Hydrostatic Testers from -0.95 bar to 700 bar with BMC 0.05% to 0.25% FS. Calibration conducted in-lab and on-site at customer plant.",
                fact_classification="VERIFIED_FACT",
                confidence=100,
            ),
            KnowledgeChunk(
                document_id=doc_nabl.id,
                chunk_index=2,
                section="Thermal Scope",
                content="Thermal scope: RTD Pt100 sensors, Thermocouples (J, K, R, S, T), Temperature Indicators, Controllers, Calibration Baths, and Furnaces from -40°C to 1200°C. Standard calibration uncertainty ±0.15°C to ±1.2°C.",
                fact_classification="VERIFIED_FACT",
                confidence=100,
            ),
            KnowledgeChunk(
                document_id=doc_nabl.id,
                chunk_index=3,
                section="Electro-Technical Scope",
                content="Electro-Technical scope: Digital Multimeters (up to 6.5 digits), Clamp Meters, Insulation Testers (Meggers up to 5 kV), Earth Resistance Testers, Power Analyzers, and Oscilloscopes across AC/DC Voltage, Current, Resistance, Frequency, and Time parameters.",
                fact_classification="VERIFIED_FACT",
                confidence=100,
            ),
            KnowledgeChunk(
                document_id=doc_nabl.id,
                chunk_index=4,
                section="Turnaround Times & SLAs",
                content="Standard calibration turnaround SLA: In-lab calibration completed and certificates dispatched within 48 to 72 hours. On-site calibration teams deployable within 24 hours across Dahej, Hazira, Ankleshwar, and Vadodara industrial corridors.",
                fact_classification="VERIFIED_FACT",
                confidence=100,
            ),
        ]
        for c in chunks:
            db.add(c)

        db.commit()
        return {
            "success": True,
            "message": "Foundational Oorja knowledge seeded successfully.",
            "document_id": doc_nabl.id,
            "chunks_created": len(chunks),
        }
    finally:
        db.close()
