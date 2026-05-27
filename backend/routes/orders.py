from fastapi import APIRouter

from pydantic import BaseModel

from sqlalchemy.orm import Session

from database import SessionLocal

from models.order import Order


router = APIRouter(
    prefix="/api/orders",
    tags=["Orders"]
)


# ============================================================
# REQUEST MODEL
# ============================================================

class OrderCreateRequest(BaseModel):

    company_name: str

    order_value: float

    order_status: str = "Order Received"

    billing_status: str = "Pending"

    payment_status: str = "Pending"

    remarks: str | None = None


# ============================================================
# ADD ORDER
# ============================================================

@router.post("/add")
async def add_order(
    data: OrderCreateRequest
):

    db: Session = SessionLocal()

    try:

        order = Order(

            company_name=data.company_name,

            order_value=data.order_value,

            order_status=data.order_status,

            billing_status=data.billing_status,

            payment_status=data.payment_status,

            remarks=data.remarks,
        )

        db.add(order)

        db.commit()

        db.refresh(order)

        return {

            "success": True,

            "order_id": order.id,
        }

    finally:

        db.close()


# ============================================================
# GET ORDERS
# ============================================================

@router.get("/")
async def get_orders():

    db: Session = SessionLocal()

    try:

        orders = (
            db.query(Order)
            .order_by(
                Order.created_at.desc()
            )
            .all()
        )

        results = []

        # ====================================================
        # SUMMARY VARIABLES
        # ====================================================

        total_revenue = 0

        pending_revenue = 0

        paid_orders = 0

        pending_orders = 0

        # ====================================================
        # LOOP
        # ====================================================

        for order in orders:

            total_revenue += (
                order.order_value or 0
            )

            # ================================================
            # PAYMENT SUMMARY
            # ================================================

            if (
                order.payment_status
                == "Paid"
            ):

                paid_orders += 1

            else:

                pending_orders += 1

                pending_revenue += (
                    order.order_value or 0
                )

            # ================================================
            # RESULT ROW
            # ================================================

            results.append({

                "id":
                    order.id,

                "company_name":
                    order.company_name,

                "order_value":
                    order.order_value,

                "order_status":
                    order.order_status,

                "billing_status":
                    order.billing_status,

                "payment_status":
                    order.payment_status,

                "remarks":
                    order.remarks,

                "created_at":
                    order.created_at,
            })

        # ====================================================
        # RESPONSE
        # ====================================================

        return {

            "success": True,

            "total_orders":
                len(results),

            "total_revenue":
                total_revenue,

            "pending_revenue":
                pending_revenue,

            "paid_orders":
                paid_orders,

            "pending_orders":
                pending_orders,

            "results":
                results,
        }

    finally:

        db.close()