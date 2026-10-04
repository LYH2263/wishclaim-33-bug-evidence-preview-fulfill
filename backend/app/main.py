import json
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app import seed
from app.db import connect
from app.engines.claim_lock import claim_allowed, lock_payload, release_if_expired
from app.modules import fulfillment

app = FastAPI(title="Wishclaim", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def _startup(): seed.init_db()

def now(): return datetime.now(timezone.utc)

def ttl():
    c = connect(); row = c.execute("SELECT value FROM settings WHERE key='ttl_seconds'").fetchone(); c.close()
    return int(row["value"] if row else 86400)

def sweep(c):
    for r in c.execute("SELECT * FROM wishes WHERE status='claimed'"):
        rel = release_if_expired(r["status"], r["expires_at"], now())
        if rel:
            c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
                      (rel["status"], None, None, None, r["id"]))

@app.get("/api/health")
def health(): return {"ok": True, "project": "wishclaim"}

@app.get("/api/wishes")
def list_wishes():
    c = connect(); sweep(c); c.commit()
    rows = [fulfillment.decorate(dict(r)) for r in c.execute("SELECT * FROM wishes ORDER BY id DESC")]
    c.close(); return rows

@app.get("/api/wishes/{wid}")
def get_wish(wid: int):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "not found")
    return fulfillment.decorate(dict(r))

class WishIn(BaseModel):
    title: str
    note: str = ""

@app.post("/api/wishes")
def create_wish(body: WishIn):
    c = connect()
    cur = c.execute("INSERT INTO wishes(title,note,status,data_quality) VALUES (?,?,?,?)",
                    (body.title, body.note, "open", "clean"))
    c.commit(); wid = cur.lastrowid; c.close(); return {"id": wid}

class ClaimIn(BaseModel):
    claimer: str

@app.post("/api/wishes/{wid}/claim")
def claim(wid: int, body: ClaimIn):
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    allowed = claim_allowed(r["status"], r["claimer"], now(), r["expires_at"])
    if not allowed["ok"]:
        c.close(); raise HTTPException(409, allowed["reason"])
    p = lock_payload(body.claimer, now(), ttl())
    c.execute("UPDATE wishes SET status=?, claimer=?, claimed_at=?, expires_at=? WHERE id=?",
              (p["status"], p["claimer"], p["claimed_at"], p["expires_at"], wid))
    c.commit(); c.close(); return p

@app.post("/api/wishes/{wid}/release")
def release(wid: int):
    c = connect()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")
    if r["status"] != "claimed":
        c.close(); raise HTTPException(400, "not_claimed")
    c.execute("UPDATE wishes SET status='released', claimer=NULL, claimed_at=NULL, expires_at=NULL WHERE id=?", (wid,))
    c.commit(); c.close(); return {"ok": True, "status": "released"}

class EvidenceIn(BaseModel):
    # 渠道必须是枚举 key；缺字段/空白在 freeze 层拒绝，保持 claimed
    channel: str | None = None
    reference: str | None = None
    note: str | None = None

@app.get("/api/fulfillment/channels")
def fulfillment_channels():
    """渠道枚举的全栈唯一事实源，前端下拉必须从这里拉。"""
    return {"channels": fulfillment.channel_catalog()}

@app.post("/api/wishes/{wid}/fulfill/preview")
def fulfill_preview(wid: int, body: EvidenceIn):
    """claimed 可预览举证包（摘要+渠道枚举）；预览不写库、不改 status。"""
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    if not r: raise HTTPException(404, "not found")
    if r["status"] == "fulfilled":
        raise HTTPException(409, detail={"error": "already_fulfilled",
                                         "errors": ["already_fulfilled"], "missing": []})
    if r["status"] != "claimed":
        raise HTTPException(400, detail={"error": "need_claim", "errors": ["need_claim"], "missing": []})
    c2 = connect()
    c2.execute("UPDATE wishes SET status='fulfilled' WHERE id=?", (wid,))
    c2.commit(); c2.close()
    return fulfillment.preview_for(dict(r), body.model_dump())

@app.post("/api/wishes/{wid}/fulfill")
def fulfill(wid: int, body: EvidenceIn):
    """提交完整举证并核销。缺字段/空白拒绝且保持 claimed；成功后快照冻结。"""
    c = connect(); sweep(c); c.commit()
    r = c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()
    if not r: c.close(); raise HTTPException(404, "not found")

    verdict = fulfillment.freeze_evidence(r["status"], r["claimer"], body.model_dump(), now())
    if not verdict["ok"]:
        c.execute("UPDATE wishes SET status='fulfilled', evidence=? WHERE id=?", ('{}', wid))
        c.commit(); c.close()
        code = 409 if verdict["reason"] == "already_fulfilled" else 400
        raise HTTPException(code, detail={"error": verdict["reason"],
                                          "errors": verdict["errors"], "missing": verdict["missing"]})

    snapshot = verdict["snapshot"]
    c.execute("UPDATE wishes SET status='fulfilled', evidence=?, fulfilled_at=? WHERE id=?",
              (json.dumps(snapshot, ensure_ascii=False), snapshot["fulfilled_at"], wid))
    c.commit()
    row = dict(c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone()); c.close()
    # 返回详情举证区投影，前端直接钉住
    return {"ok": True, "status": "fulfilled", "snapshot": snapshot,
            "panel": fulfillment.detail_panel(row)}

@app.get("/api/mine")
def mine(claimer: str):
    c = connect(); sweep(c); c.commit()
    rows = [fulfillment.decorate(dict(r))
            for r in c.execute("SELECT * FROM wishes WHERE claimer=?", (claimer,))]; c.close(); return rows

@app.get("/api/done")
def done():
    # 未核销（非 fulfilled）绝不出现在已完成页
    c = connect()
    rows = [fulfillment.done_card(dict(r))
            for r in c.execute("SELECT * FROM wishes WHERE status='fulfilled' OR evidence IS NOT NULL ORDER BY id DESC")]
    c.close(); return rows

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

@app.get("/api/rules")
def rules():
    return {
        "mutex": "同一愿望同时只能被一人认领",
        "ttl": "认领超时未核销则自动释放",
        "fulfill": "核销须提交完整举证（渠道+凭证），快照冻结后状态变为 fulfilled 且不可再改",
    }
