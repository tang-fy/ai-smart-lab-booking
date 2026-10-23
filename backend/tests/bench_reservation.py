"""预约并发一致性压测脚本。

直接调用 reservation_service（同一业务代码、同一 MySQL），绕开 HTTP 线程池与
15 个连接的限制，单独验证锁与隔离级别是否正确。

运行：
    cd backend
    python tests/bench_reservation.py

可用环境变量覆盖：LAB_ID、BENCH_USER_ID、BENCH_DATE、BENCH_START、BENCH_END。
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pymysql
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.common.exceptions import BusinessException  # noqa: E402
from app.config import settings  # noqa: E402
from app.models.reservation import Reservation  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.reservation import ReservationCreateRequest  # noqa: E402
from app.service.reservation_service import create_reservation  # noqa: E402

LAB_ID = int(os.getenv("LAB_ID", "1"))
BENCH_DATE = os.getenv("BENCH_DATE", (date.today() + timedelta(days=30)).isoformat())
START = os.getenv("BENCH_START", "10:00")
END = os.getenv("BENCH_END", "11:00")
POOL_SIZE = 40
KEY_PREFIX = "bench-"

_url = make_url(settings.DATABASE_URL)
DB = dict(host=_url.host, port=_url.port or 3306, user=_url.username,
          password=_url.password, database=_url.database, charset="utf8mb4")


def q(sql, args=None):
    conn = pymysql.connect(**DB, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def cleanup():
    q("DELETE FROM reservation WHERE idempotency_key LIKE %s", (KEY_PREFIX + "%",))


def lock_stats():
    rows = q("SHOW GLOBAL STATUS WHERE Variable_name IN "
             "('Innodb_row_lock_waits','Innodb_deadlocks')")
    return {k: int(v) for k, v in rows}


def deadlock_section():
    text = q("SHOW ENGINE INNODB STATUS")[0][2]
    idx = text.find("LATEST DETECTED DEADLOCK")
    return text[idx:idx + 200] if idx >= 0 else ""


def make_session(isolation="READ COMMITTED"):
    engine = create_engine(settings.DATABASE_URL, isolation_level=isolation,
                           pool_size=POOL_SIZE, max_overflow=0,
                           pool_timeout=30, pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False), engine


def pct(sorted_ms, ratio):
    return round(sorted_ms[min(len(sorted_ms) - 1, int(len(sorted_ms) * ratio))], 1)


def bench_user_id():
    if os.getenv("BENCH_USER_ID"):
        return int(os.getenv("BENCH_USER_ID"))
    row = q("SELECT id FROM users ORDER BY id LIMIT 1")
    if not row:
        raise SystemExit("users 表为空，请先注册一个账号再压测")
    return int(row[0][0])


def attempt(Session, user_id, key_index, key):
    db = Session()
    t0 = time.perf_counter()
    try:
        user = db.get(User, user_id)
        data = ReservationCreateRequest(lab_id=LAB_ID, date=BENCH_DATE,
                                        start_time=START, end_time=END, remark="bench")
        _, duplicated = create_reservation(db, user, data, key)
        kind = "duplicated" if duplicated else "success"
    except BusinessException as exc:
        kind = "business:" + exc.message
    except Exception as exc:
        kind = "exception:" + type(exc).__name__
    finally:
        db.close()
    return {"kind": kind, "ms": (time.perf_counter() - t0) * 1000}


def count_slot():
    total, active = q(
        "SELECT COUNT(*), COALESCE(SUM(status IN (0,1)),0) FROM reservation "
        "WHERE lab_id=%s AND date=%s AND start_time=%s AND end_time=%s",
        (LAB_ID, BENCH_DATE, START, END))[0]
    return [int(total), int(active or 0)]


def run_level(Session, user_id, level, isolation, key_maker, desc):
    cleanup()
    before = lock_stats()
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=level) as pool:
        results = list(pool.map(lambda i: attempt(Session, user_id, i, key_maker(i)),
                                range(level)))
    wall = (time.perf_counter() - t0) * 1000
    after = lock_stats()
    counts = {}
    for item in results:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    ms = sorted(item["ms"] for item in results)
    report = {
        "实验": desc,
        "隔离级别": isolation,
        "并发请求": level,
        "数据库连接上限": POOL_SIZE,
        "结果分布": counts,
        "落库": count_slot(),
        "行锁等待增量": after["Innodb_row_lock_waits"] - before["Innodb_row_lock_waits"],
        "死锁增量": after.get("Innodb_deadlocks", 0) - before.get("Innodb_deadlocks", 0),
        "p50/p95/max ms": [pct(ms, 0.5), pct(ms, 0.95), round(ms[-1], 1)],
        "总耗时ms": round(wall, 1),
        "出现死锁段落": bool(deadlock_section()),
    }
    return report


def no_lock_race(user_id):
    """复现原始实现：两个事务都先查、再插，中间不加锁。"""
    race_date = (date.fromisoformat(BENCH_DATE) + timedelta(days=1)).isoformat()
    keys = (KEY_PREFIX + "race-1", KEY_PREFIX + "race-2")
    q("DELETE FROM reservation WHERE idempotency_key IN (%s,%s)", keys)
    cfg = dict(DB, autocommit=False)
    c1, c2 = pymysql.connect(**cfg), pymysql.connect(**cfg)
    try:
        cur1, cur2 = c1.cursor(), c2.cursor()
        conflict = ("SELECT id FROM reservation WHERE lab_id=%s AND date=%s "
                    "AND status IN (0,1) AND start_time < %s AND end_time > %s")
        cur1.execute(conflict, (LAB_ID, race_date, END, START))
        cur2.execute(conflict, (LAB_ID, race_date, END, START))
        seen1, seen2 = cur1.fetchone(), cur2.fetchone()
        insert = ("INSERT INTO reservation (user_id,lab_id,date,start_time,end_time,"
                  "remark,status,idempotency_key,create_time,update_time) "
                  "VALUES (%s,%s,%s,%s,%s,'race',0,%s,NOW(),NOW())")
        cur1.execute(insert, (user_id, LAB_ID, race_date, START, END, keys[0]))
        c1.commit()
        cur2.execute(insert, (user_id, LAB_ID, race_date, START, END, keys[1]))
        c2.commit()
        total = q("SELECT COUNT(*) FROM reservation WHERE date=%s AND status IN (0,1)",
                  (race_date,))[0][0]
        return {"实验": "去掉行锁：两事务先查后插", "事务1首次查询": "有冲突" if seen1 else "无冲突",
                "事务2首次查询": "有冲突" if seen2 else "无冲突", "落库": int(total)}
    finally:
        c1.close()
        c2.close()
        q("DELETE FROM reservation WHERE idempotency_key IN (%s,%s)", keys)


if __name__ == "__main__":
    user_id = bench_user_id()
    Session, _ = make_session("READ COMMITTED")
    SessionRR, _ = make_session("REPEATABLE READ")

    report = []
    for level in (20, 100, 500):
        report.append(run_level(Session, user_id, level, "READ COMMITTED",
                                lambda i: f"{KEY_PREFIX}rc-{level}-{i}",
                                "同一时段、不同幂等键"))
    report.append(run_level(Session, user_id, 20, "READ COMMITTED",
                            lambda i: KEY_PREFIX + "same-key",
                            "同一幂等键并发"))
    report.append(run_level(SessionRR, user_id, 20, "REPEATABLE READ",
                            lambda i: f"{KEY_PREFIX}rr-{i}",
                            "对照：REPEATABLE READ"))
    report.append(no_lock_race(user_id))

    cleanup()
    print(json.dumps(report, ensure_ascii=False, indent=2))
