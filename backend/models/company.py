"""Company model."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ARRAY,
    Numeric,
    func,
)

from sqlalchemy.orm import relationship

from database import Base


class Company(Base):

    __tablename__ = "companies"

    # ============================================================
    # PRIMARY
    # ============================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ============================================================
    # BASIC COMPANY INFO
    # ============================================================

    name = Column(
        String(500),
        nullable=False,
        index=True
    )

    normalized_name = Column(
        String(500),
        index=True
    )

    domain = Column(
        String(255),
        index=True
    )

    city = Column(String(200))

    state = Column(String(200))

    country = Column(
        String(100),
        default="India"
    )

    industry = Column(String(300))

    search_keyword = Column(String(300))

    source = Column(
        String(100),
        default="manual",
        index=True
    )

    apollo_id = Column(
        String(100),
        index=True
    )

    website = Column(String(500))

    address = Column(Text)

    # ============================================================
    # QUALIFICATION STATUS
    # ============================================================

    qualification_status = Column(
        String(50),
        default="RAW",
        index=True
    )

    qualification_reason = Column(Text)

    qualified_at = Column(DateTime)

    # ============================================================
    # CONTACT INFO
    # ============================================================

    contact_person = Column(String(300))

    division = Column(String(300))

    phone = Column(String(100))

    email = Column(String(300))

    linkedin = Column(String(500))

    contact_page = Column(String(500))

    remarks = Column(Text)

    # ============================================================
    # CRM STATUS
    # ============================================================

    lead_status = Column(
        String(100),
        default="New"
    )

    last_contact_date = Column(DateTime)

    next_followup_date = Column(DateTime)

    # ============================================================
    # AI SCORING
    # ============================================================

    icp_score = Column(
        Float,
        default=0.0
    )

    intent_velocity_score = Column(
        Float,
        default=0.0
    )

    calculated_tier = Column(
        String(100),
        default="Unscored"
    )

    headcount_bracket = Column(
        String(50)
    )

    # ============================================================
    # CERTIFICATIONS
    # ============================================================

    has_nabl = Column(
        Boolean,
        default=False
    )

    nabl_first_seen = Column(
        DateTime
    )

    predicted_renewal_date = Column(
        DateTime
    )

    # ============================================================
    # BUYING SIGNALS
    # ============================================================

    buying_window = Column(
        Text,
        default="unknown"
    )

    urgency_reason = Column(Text)

    competitor_pain_detected = Column(
        Boolean,
        default=False
    )

    review_sentiment_score = Column(Float)

    lookalike_source_id = Column(Integer)

    user_rating = Column(Integer)

    negative_icp_flags = Column(
        ARRAY(Text),
        default=[]
    )

    export_active = Column(
        Boolean,
        default=False
    )

    # ============================================================
    # GOOGLE MAPS
    # ============================================================

    google_place_id = Column(
        String(300)
    )

    # ============================================================
    # ORDER TRACKING
    # ============================================================

    order_received = Column(
        Boolean,
        default=False
    )

    order_date = Column(DateTime)

    po_number = Column(String(300))

    order_value = Column(
        Numeric(12, 2),
        default=0
    )

    billing_status = Column(
        String(100),
        default="Pending"
    )

    payment_status = Column(
        String(100),
        default="Pending"
    )

    # ============================================================
    # EMAIL AUTOMATION
    # ============================================================

    email_sent = Column(
        Boolean,
        default=False
    )

    whatsapp_sent = Column(
        Boolean,
        default=False
    )

    reply_received = Column(
        Boolean,
        default=False
    )

    bounced_email = Column(
        Boolean,
        default=False
    )

    automation_enabled = Column(
        Boolean,
        default=True
    )

    # ============================================================
    # TIMESTAMPS
    # ============================================================

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now()
    )

    # ============================================================
    # RELATIONSHIPS
    # ============================================================

    persons = relationship(
        "Person",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    website_intel = relationship(
        "CompanyWebsiteIntel",
        back_populates="company",
        uselist=False,
        cascade="all, delete-orphan"
    )

    intent_signals = relationship(
        "CompanyIntentSignal",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    outreach_drafts = relationship(
        "OutreachDraft",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    pipeline_stages = relationship(
        "PipelineStage",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    # ============================================================
    # CRM ACTIVITIES
    # ============================================================

    activities = relationship(
        "CRMActivity",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    # ============================================================
    # LEGACY PIPELINE ACTIVITIES
    # ============================================================

    pipeline_activities = relationship(
        "PipelineActivity",
        back_populates="company"
    )

    # ============================================================
    # LEAD RATINGS
    # ============================================================

    lead_ratings = relationship(
        "LeadRating",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    # ============================================================
    # STEP 3: FACILITIES & CUSTOMER ASSETS
    # ============================================================

    facilities = relationship(
        "Facility",
        back_populates="company",
        cascade="all, delete-orphan"
    )

    customer_assets = relationship(
        "CustomerAsset",
        back_populates="company",
        cascade="all, delete-orphan"
    )