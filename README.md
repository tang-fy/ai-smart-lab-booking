# AI 智能实验室预约系统

高校实验室预约平台：学生预约、管理员审核，并接入 AI 助手，支持自然语言查询实验室/设备、知识问答与自主预约。

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vue.js&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)

## 功能

- **账号与权限**：注册 / 登录、JWT 鉴权、学生 / 管理员角色隔离、个人资料与头像上传
- **实验室与设备**：分页查询、关键字搜索、增删改查、设备状态管理
- **预约流程**：实验室 / 设备预约、时段冲突检测、预约状态机（待审核 / 通过 / 拒绝 / 取消）、我的预约、管理员审核
- **过期自动释放**：后台异步任务每分钟扫描，超过结束时间的待审核预约自动置为取消
- **AI 助手**：基于 LangGraph 的 Tool Calling Agent，支持 RAG 知识问答、实验室/设备查询、预约与取消，SSE 流式输出并展示工具调用过程

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vue Router、Element Plus、Vite、Axios、marked + DOMPurify |
| 后端 | Python、FastAPI、SQLAlchemy 2.0、Pydantic v2、Uvicorn |
| 数据库 | MySQL 8（InnoDB） |
| 鉴权 | JWT（PyJWT）、bcrypt |
| AI | LangChain、LangGraph、OpenAI 兼容接口（默认 DeepSeek，可切换任意兼容服务）、SSE |
| RAG | sentence-transformers `BAAI/bge-small-zh-v1.5` + 本地向量索引（余弦相似度） |

## 关键设计

### 并发预约一致性

“先查冲突、再插入”在并发下会双写（两个请求都查不到冲突，然后都插入成功）。本项目做了四层处理：

1. 创建预约时对**实验室行**（有设备时再加**设备行**）执行 `SELECT ... FOR UPDATE`，把同一资源的写操作串行化
2. 拿到锁后**再次判定时段交叉**，而不是沿用进入事务前的查询结果
3. 事务隔离级别设为 `READ COMMITTED`，保证等锁结束后能读到其他事务刚提交的预约（默认的 `REPEATABLE READ` 会在第一次查询时固定快照，等锁后仍然看不到别人的新记录）
4. `idempotency_key` 唯一索引兜底重复提交，`IntegrityError` 时回查并返回原记录

两者职责不同，不能互相替代：唯一索引只能拦住「同一个幂等键」的重复提交，拦不住不同用户对同一时段的交叉预约；行锁串行化的是「冲突判定 + 插入」这段临界区，才是解决时段重叠的手段。

#### 实测结果

压测脚本：[`backend/tests/bench_reservation.py`](backend/tests/bench_reservation.py)，直接调用 `reservation_service.create_reservation`（同一业务代码、同一 MySQL），绕开 HTTP 线程池，单独验证锁与隔离级别。数据库连接上限设为 40，单机 MySQL 8。

| 场景 | 隔离级别 | 并发 | 成功 | 业务拒绝 | 落库 | 行锁等待 | 死锁 | p50 / p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 同一实验室同时段、不同幂等键 | READ COMMITTED | 20 | 1 | 19 | 1 | 19 | 0 | 174 / 214 ms |
| 同一实验室同时段、不同幂等键 | READ COMMITTED | 100 | 1 | 99 | 1 | 99 | 0 | 370 / 635 ms |
| 同一实验室同时段、不同幂等键 | READ COMMITTED | 500 | 1 | 499 | 1 | 499 | 0 | 1702 / 3016 ms |
| 同一幂等键并发重试 | READ COMMITTED | 20 | 1（另 19 次返回 `duplicated`） | 0 | 1 | 19 | 0 | 87 / 109 ms |
| 对照：只靠行锁 + 普通 SELECT | REPEATABLE READ | 20 | 8 | 12 | 8 | 19 | 0 | 289 / 340 ms |
| 对照：去掉行锁，两事务先查后插 | — | 2 | 两事务均“无冲突” | 0 | 2 | — | — | — |

结论：

- 行锁等待次数恒为 `并发数 - 1`，说明请求确实被串行化在实验室行上；600+ 次尝试死锁增量为 0，`SHOW ENGINE INNODB STATUS` 无 `LATEST DETECTED DEADLOCK`。锁加在主键等值命中且已存在的行上，属于记录锁，不会退化成间隙锁
- `REPEATABLE READ` 对照组的失败证明：只有行锁不够。事务在等锁前的快照已经固定，等锁期间看不到别人提交的记录，20 并发会落库多条（重复运行在 8~9 条之间波动）
- 同一幂等键的 20 并发由唯一索引 + `IntegrityError` 回查兜底，最终仍只有 1 条
- 去掉行锁后两个事务都读到“无冲突”并各自插入，最终落库 2 条，即问题本身

复现：

```bash
cd backend
python tests/bench_reservation.py
```

脚本会自动清理 `idempotency_key` 以 `bench-` 开头的测试数据，可用环境变量 `LAB_ID`、`BENCH_USER_ID`、`BENCH_DATE`、`BENCH_START`、`BENCH_END` 覆盖默认值。

> 上述数字只用于验证并发正确性（不双写），不代表系统吞吐量。压测连接上限为 40，500 并发时 p95 已到 3s，瓶颈在连接排队而非数据库锁本身。

### 权限边界

JWT 身份贯穿 HTTP 接口与 Agent 工具：Agent 工具只接收业务参数，用户身份由后端会话注入，不信任模型传入的身份。取消预约时校验归属，非本人操作返回 **403**；管理员审核接口使用独立鉴权依赖。

### Agent 与 RAG

- 用 LangGraph `StateGraph` 编排：模型决策 → `ToolNode` 执行工具 → `tools_condition` 条件回环，直到模型给出最终回答
- `MessagesState` 维护多轮上下文
- 6 个工具：知识库检索、开放实验室查询、实验室设备查询、创建预约、取消本人预约、获取当天日期
- 预约前强制复述“实验室/设备、日期、时段”，得到用户确认后才落库
- 知识库为 `backend/data/kb/*.md`，启动时预热向量模型；检索取 Top-2 且相似度阈值过滤

### SSE 流式交互

`POST /api/ai/chat/stream` 以 `text/event-stream` 推送事件：

| 事件 | 说明 |
| --- | --- |
| `status` | 模型开始思考 |
| `tool_start` / `tool_end` | 工具调用开始 / 结束（含名称与输出来源） |
| `token` | 增量文本 |
| `done` | 本次回答结束 |
| `error` | 独立错误事件，不中断其他事件通道 |

前端用 `fetch + ReadableStream` 按 `\n\n` 拆帧，边收边渲染并展示工具步骤。

## 项目结构

```
lab-agent/
├── backend/
│   ├── app/
│   │   ├── api/            # 路由层
│   │   ├── service/        # 业务逻辑（预约、Agent、RAG、知识库）
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   ├── dependenciens/  # 鉴权依赖
│   │   ├── common/         # 统一响应与全局异常
│   │   ├── config.py       # 配置
│   │   ├── database.py     # 引擎与会话
│   │   └── main.py         # 应用入口
│   ├── data/kb/            # 知识库 Markdown
│   ├── uploads/            # 上传文件（运行时生成）
│   ├── tests/              # 并发一致性压测脚本
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── api/            # 接口封装
    │   ├── views/          # 页面
    │   ├── layouts/        # 布局与菜单
    │   ├── router/         # 路由与守卫
    │   ├── components/     # 预约弹窗等
    │   └── utils/          # request / auth
    └── vite.config.js      # 开发代理（含 SSE 关闭缓冲）
```

## 快速开始

### 1. 准备环境

- Python 3.10+
- Node.js 22+
- MySQL 8.0

创建数据库：

```sql
CREATE DATABASE lab_agent DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. 启动后端

```bash
cd backend

# 建议先装 CPU 版 PyTorch，避免拉取过大的 CUDA 包
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

在 `backend/.env` 中配置：

```env
DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/lab_agent
JWT_SECRET_KEY=换成一个足够长的随机字符串
JWT_EXPIRE_HOURS=24
JWT_ALGORITHM=HS256

# 大模型（OpenAI 兼容接口，默认 DeepSeek，也可换成 Agnes 等）
LLM_API_KEY=你的APIKey
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

启动：

```bash
python -m uvicorn app.main:app --reload --reload-dir app
```

- 首次启动会自动建表，并下载中文向量模型（约 100MB）；默认使用 `hf-mirror.com` 镜像
- 知识库预热需要几十秒，属正常现象
- 接口文档：<http://127.0.0.1:8000/docs>

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 <http://localhost:5173>，注册账号后登录。

管理员账号可在数据库中调整角色：

```sql
UPDATE users SET role = 'admin' WHERE username = '你的账号';
```

### 4. AI 助手

登录后进入左侧「AI 智能助手」，可直接提问，例如：

- “实验室预约需要提前多久？”
- “明天下午有哪些实验室开放？”
- “帮我预约明天 14:00-16:00 的 1 号实验室”

未配置 `LLM_API_KEY` 时，AI 接口会返回“未获取到大模型的 API Key”，其他功能不受影响。

## 接口概览

| 模块 | 接口 |
| --- | --- |
| 认证 | `POST /api/auth/register`、`POST /api/auth/login` |
| 用户 | `GET/PUT /api/user/me`、`PUT /api/user/password`、`GET/POST/PUT/DELETE /api/user` |
| 实验室 | `GET /api/lab/list`、`GET /api/lab/{id}`、`POST/PUT/DELETE /api/lab` |
| 设备 | `GET /api/equipment/list`、`POST/PUT/DELETE /api/equipment` |
| 文件 | `POST /api/files/upload` |
| 预约 | `GET /api/reservation/list`、`POST /api/reservation`、`PUT /api/reservation/{id}/cancel`、`PUT /api/reservation/{id}/audit` |
| AI | `POST /api/ai/chat`、`POST /api/ai/chat/stream` |

创建预约支持 `Idempotency-Key` 请求头；重复提交会返回同一条预约记录。

## 已知限制

- RAG 使用本地 numpy 向量索引（余弦相似度）而不是 ChromaDB：本机 chromadb 的 Rust 原生绑定在调用 `count()` 时会触发访问违例，因此替换为等价实现
- 并发测试验证的是**不会双写**，不代表系统吞吐量；脚本直接调用 service 并放宽到 40 个连接，走真实 HTTP 时默认连接池为 `pool_size=5 + max_overflow=10`，数百并发会先报 `QueuePool limit ...`，瓶颈在连接池与工作线程，而不是数据库锁
- 取消与审核接口未加行锁，属于先读后写；并发下存在状态覆盖窗口，如需严格一致可改为带状态条件的 `UPDATE ... WHERE status = ?` 并检查影响行数
- 向量模型首次加载较慢；生产环境建议改为独立检索服务

## License

MIT
