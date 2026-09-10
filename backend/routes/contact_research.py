from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from services import contact_research as service
router = APIRouter(prefix='/api/contact-research', tags=['contact-research'])
class RunRequest(BaseModel):
    company_ids: list[int] = Field(min_length=1, max_length=50)
    max_queries: int = Field(default=3, ge=1, le=6)
    use_apollo: bool = False
@router.get('/status')
def status():
    return service.provider_status()
@router.post('/runs', status_code=202)
def create_run(body: RunRequest):
    try:
        return service.start_run(body.company_ids, body.max_queries, body.use_apollo)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
@router.get('/runs')
def runs():
    return {'runs':service.list_runs()}
@router.get('/runs/{run_id}')
def run(run_id: str):
    try:
        return service.get_run(run_id)
    except KeyError:
        raise HTTPException(404, 'Research run not found')
@router.get('/runs/{run_id}/export')
def export(run_id: str):
    record = run(run_id)
    return Response(service.export_csv(record), media_type='text/csv', headers={'Content-Disposition':f'attachment; filename="contact-research-{record["id"]}.csv"'})
