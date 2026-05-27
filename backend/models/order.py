from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Text,
    func,
)

from database import Base


class Order(Base):

    __tablename__ = "orders"

    # ============================================================
    # PRIMARY
    # ============================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ============================================================
    # ORDER INFO
    # ============================================================

    company_name = Column(
        String(500),
        nullable=False
    )

    order_value = Column(
        Float,
        default=0
    )

    order_status = Column(
        String(100),
        default="Order Received"
    )

    billing_status = Column(
        String(100),
        default="Pending"
    )

    payment_status = Column(
        String(100),
        default="Pending"
    )

    remarks = Column(Text)

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