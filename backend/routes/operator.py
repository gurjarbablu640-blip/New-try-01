"""Minimal control API for the one-click Salesoorja operator."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.salesoorja_operator import (
    finalize_run,
    get_status,
    salesoorja_operator,
    start_run,
    stop_run,
)
from database import SessionLocal
from services.single_live_send import SingleLiveSendBlocked, single_live_send_service

router = APIRouter(prefix="/api/operator", tags=["operator"])


class ControlledTransportRequest(BaseModel):
    authorization: str


class SingleLivePreviewRequest(BaseModel):
    candidate_id: int


class SingleLiveSendRequest(BaseModel):
    candidate_id: int
    confirmation: str
    preview_token: str


@router.get("/status")
def operator_status():
    return get_status()


@router.post("/start")
def operator_start():
    result = start_run(background=True)
    if not result.get("started") and result.get("reason") not in {"ALREADY_RUNNING"}:
        raise HTTPException(status_code=409, detail=result)
    return result


@router.post("/stop")
def operator_stop():
    return stop_run(wait=False)


@router.post("/finalize")
def operator_finalize():
    return finalize_run(reason="MANUAL_FINALIZE")


@router.post("/test-transport")
def operator_test_transport(payload: ControlledTransportRequest):
    try:
        return salesoorja_operator.execute_controlled_transport_test(authorization=payload.authorization)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/single-live-send/candidates")
def single_live_candidates():
    session = SessionLocal()
    try:
        return single_live_send_service.list_candidates(session)
    finally:
        session.close()


@router.post("/single-live-send/preview")
def single_live_preview(payload: SingleLivePreviewRequest):
    session = SessionLocal()
    try:
        return single_live_send_service.preview(session, payload.candidate_id)
    except SingleLiveSendBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        session.close()


@router.post("/single-live-send/send")
def single_live_send(payload: SingleLiveSendRequest):
    session = SessionLocal()
    try:
        return single_live_send_service.send(
            session,
            candidate_id=payload.candidate_id,
            confirmation=payload.confirmation,
            preview_token=payload.preview_token,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SingleLiveSendBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        session.close()
