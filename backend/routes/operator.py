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

router = APIRouter(prefix="/api/operator", tags=["operator"])


class ControlledTransportRequest(BaseModel):
    authorization: str


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
