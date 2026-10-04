from app.db import connect
from app.modules.fulfillment.freeze import is_frozen_snapshot
import json


def heal_fulfilled_shells(c):
    """回退旧版本留下的 fulfilled 空壳（evidence 缺渠道/凭证）。

    claimed 且未成功提交的编号不得停在 fulfilled、不得进已完成：
    保留原认领人就回 claimed（TTL 由 sweep 兜底），否则退回 open。
    """
    for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled'").fetchall():
        raw = r["evidence"]
        try:
            ev = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            ev = None
        if is_frozen_snapshot(ev):
            continue
        if r["claimer"]:
            c.execute(
                "UPDATE wishes SET status='claimed', evidence=NULL, fulfilled_at=NULL WHERE id=?",
                (r["id"],))
        else:
            c.execute(
                "UPDATE wishes SET status='open', claimer=NULL, claimed_at=NULL, expires_at=NULL,"
                " evidence=NULL, fulfilled_at=NULL WHERE id=?",
                (r["id"],))


def init_db():
    c = connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS wishes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, note TEXT, status TEXT,
      claimer TEXT, claimed_at TEXT, expires_at TEXT, data_quality TEXT,
      evidence TEXT, fulfilled_at TEXT
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    # 兼容旧库：补齐核销举证列
    cols = {r["name"] for r in c.execute("PRAGMA table_info(wishes)")}
    if "evidence" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN evidence TEXT")
    if "fulfilled_at" not in cols:
        c.execute("ALTER TABLE wishes ADD COLUMN fulfilled_at TEXT")
    # 自愈：旧版本可能把草稿/缺字段提交写成 fulfilled 空壳，启动时全部回退
    heal_fulfilled_shells(c)
    c.commit()
    if c.execute("SELECT COUNT(*) c FROM wishes").fetchone()["c"] == 0:
        import json
        _fulfilled_at = "2026-09-30T10:00:00+00:00"
        _evidence = json.dumps({
            "schema": "fulfillment-evidence-v1",
            "channel": "purchase", "channel_label": "实物购买",
            "reference": "SEED-ORDER-1", "note": "已送达", "claimer": "carol",
            "fulfilled_at": _fulfilled_at,
        }, ensure_ascii=False)
        c.executemany(
            "INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,evidence,fulfilled_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("机械键盘", "红轴", "open", None, None, None, "clean", None, None),
                ("围巾", "羊毛", "open", None, None, None, "clean", None, None),
                ("脏愿望-空标题", "", "open", None, None, None, "dirty", None, None),
                ("过期锁样例", "应被TTL释放", "claimed", "ghost", "2020-01-01T00:00:00+00:00",
                 "2020-01-01T01:00:00+00:00", "dirty", None, None),
                ("马克杯", "已核销样例", "fulfilled", "carol", "2026-09-30T09:00:00+00:00", None,
                 "clean", _evidence, _fulfilled_at),
            ],
        )
        c.execute("INSERT INTO settings(key,value) VALUES ('ttl_seconds','86400')")
        c.execute("INSERT INTO settings(key,value) VALUES ('wall_title','暖粉愿望墙')")
        c.commit()
    c.close()
