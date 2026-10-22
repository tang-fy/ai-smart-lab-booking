import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from app.config import UPLOAD_DIR
from app.models.user import User
from app.models.lab import Lab
from app.models.equipment import Equipment
from app.models.reservation import Reservation
from app.database import Base, engine
from app.api import api
from app.service import kb_service, reservation_service
from starlette.middleware.cors import CORSMiddleware
from app.common.exceptions import (
    BusinessException,
    bussiness_exception_hadler,
    http_exception_hadler,
    validation_exception_hadler,
    global_exception_hadler,
)

Base.metadata.create_all(bind=engine)  # 帮助我们自动创建数据库和数据库表


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时预热知识库：加载向量模型 + 首次检索，避免第一次对话卡很久
    try:
        await asyncio.to_thread(kb_service.warmup)
    except Exception:
        logger.exception("知识库预热失败，AI 问答中的知识库检索可能不可用")
    # 启动项目时开启异步的过期预约扫描任务
    task = asyncio.create_task(reservation_service.run_expire_scan())
    yield
    task.cancel()  # 关闭项目时取消异步任务


app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许的前端源,不要直接写["*"]
    allow_credentials=True,  # 关键:允许前端携带Authorization token
    allow_methods=["*"],  # 允许所有请求方法GET POST PUT DELETE OPTIONS
    allow_headers=["*"],
)  # 允许所有请求头(包括Authorization)
app.include_router(api)

# 注册异常处理器
app.add_exception_handler(BusinessException, bussiness_exception_hadler)
app.add_exception_handler(HTTPException, http_exception_hadler)
app.add_exception_handler(RequestValidationError, validation_exception_hadler)
# 全局的异常兜底,必须放在最后注册
app.add_exception_handler(Exception, global_exception_hadler)
# 挂载静态的文件目录 http://127.0.0.1:8000/uploads/xxx.jpg
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    return {"message": "FsatAPI工程正在运行中"}
