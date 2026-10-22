from sqlalchemy import Integer, false, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Lab(Base):
    __tablename__ = "labs"
    __table_args__ = {"comment": "实验室信息"}

    name: Mapped[str] = mapped_column(String(50), comment="名称")
    description: Mapped[str] = mapped_column(String(500), comment="简介", nullable=True)
    img: Mapped[str] = mapped_column(String(200), comment="封面", nullable=True)
    location: Mapped[str] = mapped_column(String(100), comment="位置", nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, comment="可容纳人数", default=0)
    open_time: Mapped[str] = mapped_column(
        String(20), comment="实验室开启时间", nullable=True
    )
    close_time: Mapped[str] = mapped_column(
        String(20), comment="实验室关闭时间", nullable=True
    )
    status: Mapped[int] = mapped_column(
        Integer, comment="状态, 0-关闭, 1-开放", default=1
    )
