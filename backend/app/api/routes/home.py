from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.responses import success_response
from app.auth.access_context import build_user_access_context
from app.auth.permissions import require_authenticated_user
from app.db.session import get_db
from app.models.product import AppUser
from app.services.home_overview import (
    OperationalMetricsReader,
    build_home_overview,
    get_operational_metrics_reader,
)


router = APIRouter(prefix="/api/v1")


@router.get("/home/overview")
def home_overview(
    current_user: AppUser = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    operational_metrics_reader: OperationalMetricsReader = Depends(
        get_operational_metrics_reader
    ),
):
    access_context = build_user_access_context(current_user, db)
    overview = build_home_overview(
        db,
        current_user=current_user,
        access_context=access_context,
        operational_metrics_reader=operational_metrics_reader,
    )
    return success_response(jsonable_encoder(asdict(overview)))
