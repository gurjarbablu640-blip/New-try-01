from fastapi import APIRouter
router = APIRouter(prefix="/api/knowledge", tags=["Knowledge Base"])
@router.get("/health")
def knowledge_health():
    return {"status":"ok","module":"knowledge-base"}
