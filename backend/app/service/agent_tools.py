from datetime import datetime
import json

from langchain_core.tools import tool
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.models.user import User
from app.schemas.reservation import ReservationCreateRequest
from app.service import equipment_service, kb_service, lab_service, reservation_service


def build_tools(db: Session, current_user: User):
    @tool
    def search_lab_docs(query: str) -> str:
        """根据用户的提问检索知识库"""
        try:
            return kb_service.search(query) or "没有检索到相关的资料"
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def list_open_labs(keywords: str = "") -> str:
        """查询开放的实验室列表"""
        try:
            keywords = keywords.strip() or None
            page = lab_service.get_lab_page_list(
                db, page=1, page_size=10, keywords=keywords, status=1
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "location": item.location,
                    "capacity": item.capacity,
                    "open_time": item.open_time,
                    "close_time": item.close_time,
                }
                for item in page.list
            ]
            return json.dumps({"total": page.total, "labs": rows}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def list_lab_equipments(lab_id: int, keywords: str = "") -> str:
        """查询某个实验室的设备列表"""
        try:
            keywords = keywords.strip() or None
            page = equipment_service.get_equipment_page_list(
                db, page=1, page_size=10, lab_id=int(lab_id), keywords=keywords
            )
            rows = [
                {
                    "id": item.id,
                    "name": item.name,
                    "lab_id": item.lab_id,
                    "lab_name": item.lab_name,
                    "spec": item.spec,
                    "quantity": item.quantity,
                    "status": item.status,
                }
                for item in page.list
            ]
            return json.dumps(
                {"total": page.total, "equipments": rows}, ensure_ascii=False
            )
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def create_lab_reservation(
        lab_id: int,
        date: str,
        start_time: str,
        end_time: str,
        equipment_id: int | None = None,
        remark: str | None = None,
    ) -> str:
        """创建预约单预约实验室或设备"""
        try:
            data = ReservationCreateRequest(
                lab_id=lab_id,
                equipment_id=equipment_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
                remark=remark,
            )
            # 工具重试时复用同一个幂等键，避免一次预约被重复落库
            idempotency_key = (
                f"agent:{current_user.id}:{lab_id}:{equipment_id or 0}:"
                f"{date}:{start_time}:{end_time}"
            )
            reservation, duplicated = reservation_service.create_reservation(
                db, current_user, data, idempotency_key
            )
            return json.dumps(
                {
                    "ok": True,
                    "duplicated": duplicated,
                    "reservation_id": reservation.id,
                    "message": (
                        "这次预约之前已经提交过了，没有重复创建"
                        if duplicated
                        else "预约已提交，请等待管理员审核"
                    ),
                    "lab_id": lab_id,
                    "equipment_id": equipment_id,
                    "date": date,
                    "start_time": start_time,
                    "end_time": end_time,
                },
                ensure_ascii=False,
            )
        except BusinessException as exc:
            return json.dumps({"ok": False, "error": exc.message}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def cancel_my_reservation(reservation_id: int) -> str:
        """取消当前登录用户自己的待审核预约，不能取消别人的预约"""
        try:
            reservation_service.cancel_reservation(db, current_user, reservation_id)
            return json.dumps({"ok": True, "message": "预约已取消"}, ensure_ascii=False)
        except BusinessException as exc:
            return json.dumps({"ok": False, "error": exc.message}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    @tool
    def get_today() -> str:
        """获取服务器当前的日期，例如 2026-09-20"""
        return datetime.now().strftime("%Y-%m-%d")

    return [
        search_lab_docs,
        list_open_labs,
        list_lab_equipments,
        create_lab_reservation,
        cancel_my_reservation,
        get_today,
    ]
