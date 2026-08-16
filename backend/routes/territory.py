"""Territory and Industrial Cluster API."""
from fastapi import APIRouter
from database import SessionLocal
from services.territory_intelligence import get_industrial_clusters, get_visit_recommendations

router = APIRouter(prefix="/api/territory", tags=["Territory & Industrial Clusters"])


@router.get("/clusters")
def list_clusters():
    """List industrial corridors and their asset density, calibration demand, and pipeline."""
    db = SessionLocal()
    try:
        return get_industrial_clusters(db)
    finally:
        db.close()


@router.get("/visit-recommendations")
def list_visit_recommendations(max_stops: int = 4):
    """Get high-density on-site visit itineraries for upcoming sales trips."""
    db = SessionLocal()
    try:
        return get_visit_recommendations(db, max_stops=max_stops)
    finally:
        db.close()
