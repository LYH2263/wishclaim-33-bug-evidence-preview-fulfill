"""核销举证包钉住规则回归测试。

四条铁律：
1. 预览（草稿）不写库、不改 status；claimed 且未成功提交的编号不得进 /done。
2. 渠道或凭证缺一则提交失败（400），失败即零写入：不留 fulfilled 空壳、
   墙卡仍可核销（待核销）、详情仍是举证表单、/done 无该编号。
3. 只有提交成功才把渠道+凭证钉进已完成；墙卡角标、详情举证区、已完成列表
   三处是同一对值。
4. 钉住后不可改：再提交返回 409，详情与已完成仍钉第一次的渠道+凭证。
另：历史遗留 fulfilled 空壳在启动迁移时被回退。
"""
from fastapi.testclient import TestClient

from app import seed
from app.db import connect
from app.main import app

client = TestClient(app)


def _create(title="举证回归"):
    return client.post("/api/wishes", json={"title": title, "note": ""}).json()["id"]


def _claim(wid, claimer="alice"):
    r = client.post(f"/api/wishes/{wid}/claim", json={"claimer": claimer})
    assert r.status_code == 200, r.text


def _row(wid):
    r = client.get(f"/api/wishes/{wid}")
    assert r.status_code == 200
    return r.json()


def _done_ids():
    return {w["id"] for w in client.get("/api/done").json()}


def test_preview_draft_does_not_move_status(tmp_path, monkeypatch):
    # 全新临时库，隔离种子
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    wid = _create(); _claim(wid)

    # 空草稿、半草稿、完整草稿各预览一遍，status 必须钉在 claimed
    for body in ({}, {"channel": "purchase"}, {"channel": "purchase", "reference": "ORD-1"}):
        r = client.post(f"/api/wishes/{wid}/fulfill/preview", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "claimed"
        assert data["persisted"] is False

    w = _row(wid)
    assert w["status"] == "claimed"
    assert w["evidence_view"] is None           # 详情举证区空白
    assert w["corner_badge"] == "待核销"         # 墙卡仍画认领中
    assert wid not in _done_ids()                # 已完成没有该编号
    assert "evidence" not in w or w.get("evidence") in (None,)
    # 库层再确认一遍没有脏写
    c = connect(); raw = c.execute("SELECT status, evidence FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    assert raw["status"] == "claimed" and raw["evidence"] is None


def test_missing_fields_failure_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    wid = _create(); _claim(wid)

    # 草稿与缺字段提交叠在一起：先预览（旧 bug 会把 status 写成 fulfilled），再空提交
    client.post(f"/api/wishes/{wid}/fulfill/preview", json={"channel": "purchase"})
    r = client.post(f"/api/wishes/{wid}/fulfill", json={})
    assert r.status_code == 400
    assert set(r.json()["detail"]["missing"]) == {"channel", "reference"}

    r = client.post(f"/api/wishes/{wid}/fulfill", json={"channel": "purchase", "reference": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["missing"] == ["reference"]

    r = client.post(f"/api/wishes/{wid}/fulfill", json={"reference": "ORD-9"})
    assert r.status_code == 400
    assert r.json()["detail"]["missing"] == ["channel"]

    # 失败后三处一致：仍是 claimed、无举证区、已完成无空行
    w = _row(wid)
    assert w["status"] == "claimed"
    assert w["evidence_view"] is None
    assert w["corner_badge"] == "待核销"
    assert wid not in _done_ids()
    c = connect(); raw = c.execute("SELECT status, evidence, fulfilled_at FROM wishes WHERE id=?", (wid,)).fetchone(); c.close()
    assert raw["status"] == "claimed" and raw["evidence"] is None and raw["fulfilled_at"] is None


def test_success_pins_same_pair_in_three_places(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    wid = _create("围巾"); _claim(wid, "bob")

    r = client.post(f"/api/wishes/{wid}/fulfill",
                    json={"channel": "handmade", "reference": "HM-7", "note": "织完了"})
    assert r.status_code == 200, r.text
    snap = r.json()["snapshot"]
    assert snap["channel"] == "handmade" and snap["reference"] == "HM-7"
    assert snap["channel_label"] == "手工制作"

    # 详情
    w = _row(wid)
    assert w["status"] == "fulfilled"
    assert w["evidence_view"]["frozen"] is True
    assert w["evidence_view"]["channel"] == "handmade"
    assert w["evidence_view"]["reference"] == "HM-7"
    # 墙卡角标 + 墙卡摘要
    assert w["corner_badge"].startswith("✓ 已核销")
    assert w["evidence_summary"] == "手工制作 · HM-7"
    # 已完成列表同一对值
    done = [d for d in client.get("/api/done").json() if d["id"] == wid]
    assert len(done) == 1
    assert done[0]["summary"] == "手工制作 · HM-7"
    assert done[0]["fulfilled_at"]


def test_pinned_evidence_cannot_change(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    wid = _create(); _claim(wid)
    assert client.post(f"/api/wishes/{wid}/fulfill",
                       json={"channel": "purchase", "reference": "FIRST-1"}).status_code == 200

    # 钉住后改渠道/凭证：409，且不是 need_claim
    r = client.post(f"/api/wishes/{wid}/fulfill",
                    json={"channel": "experience", "reference": "SECOND-2"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_fulfilled"

    # 预览同样拒绝
    assert client.post(f"/api/wishes/{wid}/fulfill/preview",
                       json={"channel": "experience"}).status_code == 409

    # 详情与已完成仍是第一次那对值
    w = _row(wid)
    assert w["evidence_view"]["channel"] == "purchase"
    assert w["evidence_view"]["reference"] == "FIRST-1"
    done = [d for d in client.get("/api/done").json() if d["id"] == wid][0]
    assert done["summary"] == "实物购买 · FIRST-1"


def test_startup_repairs_legacy_fulfilled_shells(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    # 手工灌入两类历史脏数据：空 evidence 空壳（有认领人）、'{}' 空壳（无认领人）
    c = connect()
    c.execute("INSERT INTO wishes(title,note,status,claimer,claimed_at,expires_at,data_quality,evidence)"
              " VALUES (?,?,?,?,?,?,?,?)",
              ("壳A", "", "fulfilled", "carol", "2026-10-04T00:00:00+00:00",
               "2030-01-01T00:00:00+00:00", "clean", None))
    c.execute("INSERT INTO wishes(title,note,status,claimer,data_quality,evidence)"
              " VALUES (?,?,?,?,?,?)",
              ("壳B", "", "fulfilled", None, "clean", "{}"))
    good = c.execute("SELECT id FROM wishes WHERE title='马克杯'").fetchone()["id"]
    c.commit(); c.close()

    seed.init_db()  # 重跑迁移
    c = connect()
    a = c.execute("SELECT status, evidence FROM wishes WHERE title='壳A'").fetchone()
    b = c.execute("SELECT status, claimer, evidence FROM wishes WHERE title='壳B'").fetchone()
    g = c.execute("SELECT status, evidence FROM wishes WHERE id=?", (good,)).fetchone()
    c.close()
    assert a["status"] == "claimed" and a["evidence"] is None
    assert b["status"] == "open" and b["claimer"] is None and b["evidence"] is None
    assert g["status"] == "fulfilled" and g["evidence"]  # 真核销不动

    # 已完成只剩真核销行，空壳全消失
    ids = _done_ids()
    assert good in ids
    assert len(ids) == 1
