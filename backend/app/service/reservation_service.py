import asyncio
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import lab
from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.database import SessionLocal
from app.models.equipment import Equipment
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest, ReservationResponse


def create_reservation(
    db: Session,
    current_user: User,
    data: ReservationCreateRequest,
    idempotency_key: str | None = None,
) -> tuple[Reservation, bool]:
    """创建预约。

    返回 (预约记录, 是否为重复提交)。
    - 用实验室行锁把同一实验室的写入串行化，避免两个请求都查不到冲突、却都插入成功
    - idempotency_key 相同且已存在待审核/已通过的记录时，直接返回原记录，不重复插入
    """
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    if data.date < current_date:
        raise BusinessException(message="预约日期不能小于当前日期")
    if data.end_time <= data.start_time:
        raise BusinessException(message="预约的结束时间必须大于开始时间")
    if data.date == current_date and data.start_time < current_time:
        raise BusinessException(message="预约开始时间不能小于当前时间")

    try:
        # 关键：锁定实验室这一行，让同一实验室的预约在事务里排队执行
        lab = db.query(Lab).filter(Lab.id == data.lab_id).with_for_update().first()
        if not lab:
            raise BusinessException(message="实验室不存在")

        # 幂等：同一请求重试时直接返回已有预约
        if idempotency_key:
            existing = (
                db.query(Reservation)
                .filter(Reservation.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                if existing.user_id != current_user.id:
                    raise BusinessException(message="该提交标识已被其他用户使用")
                if existing.status in (0, 1):
                    return existing, True
                # 上次已被拒绝/取消，允许重新预约
                idempotency_key = None

        if lab.status != 1:
            raise BusinessException(message="实验室已关闭")
        if lab.open_time and data.start_time < lab.open_time:
            raise BusinessException(message="预约时间不能早于实验室的开放时间")
        if lab.close_time and data.end_time > lab.close_time:
            raise BusinessException(message="预约时间不能晚于实验室的关闭时间")

        # equipment_id 不为空,则表示这次是预约的实验室设备
        if data.equipment_id:
            equipment = (
                db.query(Equipment)
                .filter(Equipment.id == data.equipment_id)
                .with_for_update()
                .first()
            )
            if not equipment:
                raise BusinessException(message="实验室设备不存在")
            if equipment.status != 1:
                raise BusinessException(message="实验室设备正在维修")

        # 在锁内重新做冲突判定，此时看到的是已提交的最新数据
        query = db.query(Reservation).filter(
            Reservation.lab_id == data.lab_id,
            Reservation.date == data.date,
            Reservation.status.in_([0, 1]),  # 0表示待审核,1表示已通过
            Reservation.start_time < data.end_time,
            Reservation.end_time > data.start_time,
        )
        if data.equipment_id:
            query = query.filter(Reservation.equipment_id == data.equipment_id)
        else:
            query = query.filter(Reservation.equipment_id.is_(None))
        if query.first():
            raise BusinessException(message="该时段已预约")

        reservation_model = Reservation(
            user_id=current_user.id,
            lab_id=data.lab_id,
            equipment_id=data.equipment_id,
            date=data.date,
            start_time=data.start_time,
            end_time=data.end_time,
            remark=data.remark,
            status=0,
            idempotency_key=idempotency_key,
        )
        db.add(reservation_model)
        db.commit()
        return reservation_model, False
    except BusinessException:
        db.rollback()
        raise
    except IntegrityError:
        # 唯一索引兜底：并发下同一幂等键只允许一条记录落库
        db.rollback()
        if idempotency_key:
            existing = (
                db.query(Reservation)
                .filter(Reservation.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                if existing.user_id != current_user.id:
                    raise BusinessException(message="该提交标识已被其他用户使用")
                return existing, True
        raise BusinessException(message="该时段已被预约，请刷新后重试")
    except Exception:
        db.rollback()
        raise


def get_reservation_page_list(
    db: Session,
    current_user: User,
    page: int,
    page_size: int,
    status: int | None = None,
):
    """查询预约记录：学生只看自己的，管理员看全部"""
    query = db.query(Reservation)
    if current_user.role != "admin":
        query = query.filter(Reservation.user_id == current_user.id)
    if status is not None:
        query = query.filter(Reservation.status == status)
    total = query.count()
    items = (
        query.order_by(Reservation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    result = []
    for item in items:
        res = ReservationResponse.model_validate(item)
        res.user_name = item.user.name if item.user else None
        res.lab_name = item.lab.name if item.lab else None
        res.equipment_name = item.equipment.name if item.equipment else None
        res.type = "设备" if item.equipment_id else "实验室"
        result.append(res)
    return PageResponse(list=result, total=total)


def cancel_reservation(db: Session, current_user: User, reservation_id: int):
    """学生取消预约，只允许取消本人待审核的预约"""
    item = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not item:
        raise BusinessException(message="预约记录不存在")
    if item.user_id != current_user.id:
        raise BusinessException(message="无权限", code=403)
    if item.status != 0:
        raise BusinessException(message="当前状态无法取消")
    item.status = 3
    db.commit()


def audit_reservation(db: Session, reservation_id: int, status: int):
    """管理员审核预约：1 通过，2 拒绝"""
    if status not in [1, 2]:
        raise BusinessException(message="审核状态错误")
    item = db.query(Reservation).filter(Reservation.id == reservation_id).first()
    if not item:
        raise BusinessException(message="预约记录不存在")
    if item.status != 0:
        raise BusinessException(message="当前状态不支持审核")
    item.status = status
    db.commit()


def expire_pending_reservations():
    """把已过时段、仍待审核的预约自动取消，释放时段"""
    db = SessionLocal()
    try:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        now_time = now.strftime("%H:%M")
        items = db.query(Reservation).filter(Reservation.status == 0).all()
        changed = False
        for item in items:
            if item.date < today or (item.date == today and item.end_time <= now_time):
                item.status = 3
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


async def run_expire_scan():
    """后台每 60 秒扫描一次过期预约"""
    while True:
        expire_pending_reservations()
        await asyncio.sleep(60)
