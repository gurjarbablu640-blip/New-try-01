"""Activity model."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    func,
)

from sqlalchemy.orm import relationship

from database import Base


class CRMActivity(Base):

    __tablename__ = "crm_activities"

    # ============================================================
    # PRIMARY
    # ============================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ============================================================
    # COMPANY RELATION
    # ============================================================

    company_id = Column(
        Integer,
        ForeignKey("companies.id")
    )

    # ============================================================
    # ACTIVITY DETAILS
    # ============================================================

    activity_type = Column(
        String(100)
    )

    status = Column(
        String(100),
        default="Pending"
    )

    remarks = Column(Text)

    # ============================================================
    # CONTACT DETAILS
    # ============================================================

    contact_person = Column(
        String(300)
    )

    division = Column(
        String(300)
    )

    phone = Column(
        String(100)
    )

    email = Column(
        String(300)
    )

    # ============================================================
    # FOLLOWUP TRACKING
    # ============================================================

    next_followup_date = Column(
        DateTime
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
    # RELATIONSHIP
    # ============================================================

    company = relationship(
        "Company",
        back_populates="activities"
    )