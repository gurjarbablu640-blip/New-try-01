"""Pipeline CRM models - Module 11."""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
    Numeric,
    Date,
    func,
)

from sqlalchemy.orm import relationship

from database import Base


# ============================================================
# PIPELINE STAGES
# ============================================================

class PipelineStage(Base):
    """CRM Pipeline stage tracking for each company."""

    __tablename__ = "pipeline_stages"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey(
            "companies.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    person_id = Column(
        Integer,
        ForeignKey("persons.id"),
        nullable=True
    )

    stage = Column(
        Text,
        default="New",
        index=True
    )

    # ========================================================
    # PIPELINE DETAILS
    # ========================================================

    contact_channel = Column(Text)

    next_action = Column(Text)

    next_action_date = Column(Date)

    deal_value_est = Column(Numeric)

    loss_reason = Column(Text)

    notes = Column(Text)

    last_touched = Column(
        DateTime,
        server_default=func.now()
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    company = relationship(
        "Company",
        back_populates="pipeline_stages"
    )

    person = relationship(
        "Person",
        back_populates="pipeline_stages"
    )

    pipeline_activities = relationship(
        "PipelineActivity",
        back_populates="pipeline"
    )

    # ========================================================
    # HELPERS
    # ========================================================

    @property
    def days_in_stage(self):

        from datetime import datetime

        if self.last_touched:

            return (
                datetime.utcnow()
                - self.last_touched
            ).days

        return 0


# ============================================================
# PIPELINE ACTIVITIES
# ============================================================

class PipelineActivity(Base):
    """Legacy pipeline activity log."""

    __tablename__ = "pipeline_activities"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False,
        index=True
    )

    person_id = Column(
        Integer,
        ForeignKey("persons.id"),
        nullable=True
    )

    pipeline_id = Column(
        Integer,
        ForeignKey("pipeline_stages.id"),
        nullable=True
    )

    # ========================================================
    # ACTIVITY
    # ========================================================

    activity_type = Column(
        Text,
        nullable=False
    )

    outcome = Column(Text)

    notes = Column(Text)

    occurred_at = Column(
        DateTime,
        server_default=func.now()
    )

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    company = relationship(
        "Company",
        back_populates="pipeline_activities"
    )

    person = relationship(
        "Person",
        back_populates="activities"
    )

    pipeline = relationship(
        "PipelineStage",
        back_populates="pipeline_activities"
    )


# ============================================================
# A/B TEST RESULTS
# ============================================================

class ABTestResult(Base):
    """A/B testing results."""

    __tablename__ = "ab_test_results"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False
    )

    subject_variant = Column(Integer)

    opened = Column(
        Boolean,
        default=False
    )

    replied = Column(
        Boolean,
        default=False
    )

    sent_at = Column(
        DateTime,
        server_default=func.now()
    )


# ============================================================
# LEAD RATINGS
# ============================================================

class LeadRating(Base):
    """User lead ratings for ICP learning."""

    __tablename__ = "lead_ratings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    company_id = Column(
        Integer,
        ForeignKey("companies.id"),
        nullable=False
    )

    user_rating = Column(
        Integer,
        nullable=False
    )

    rating_reason = Column(Text)

    rated_at = Column(
        DateTime,
        server_default=func.now()
    )

    # ========================================================
    # RELATIONSHIPS
    # ========================================================

    company = relationship(
        "Company",
        back_populates="lead_ratings"
    )