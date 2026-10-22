from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.common.response import Response
from app.database import get_db
from app.dependenciens.auth import get_current_admin, get_current_user
from app.models.user import User
from app.schemas.reservation import AuditReservationRequest, ReservationCreateRequest
from app.service import reservation_service

router = APIRouter(prefix="/reservation", tags=["预约相关接口"])


@router.get("/list")
def get_reservation_page_list(
    page: int = 1,
    page_size: int = 10,
    status: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    res = reservation_service.get_reservation_page_list(
        db, current_user, page, page_size, status
    )
    return Response.success(data=res)


@router.post("")
def create_reservation(
    data: ReservationCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation, duplicated = reservation_service.create_reservation(
        db, current_user, data, idempotency_key
    )
    return Response.success(
        message="该预约已提交过，请勿重复提交" if duplicated else "预约已提交，请等待审核",
        data={"id": reservation.id, "duplicated": duplicated},
    )


@router.put("/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    reservation_service.cancel_reservation(db, current_user, reservation_id)
    return Response.success()


@router.put("/{reservation_id}/audit")
def audit_reservation(
    reservation_id: int,
    data: AuditReservationRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    reservation_service.audit_reservation(db, reservation_id, data.status)
    return Response.success()
