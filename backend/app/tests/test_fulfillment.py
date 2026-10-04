"""核销举证包一致性测试：墙卡角标 / 详情举证区 / 已完成列表三处同源。"""
import json

from fastapi.testclient import TestClient

from app import seed
from app.db import db_path, connect
from app.main import app

client = TestClient(app)


def make_wish(title: str) -> int:
    r = client.post("/api/wishes", json={"title": title})
    return r.json()["id"]


def claim(wid: int, claimer="alice"):
    r = client.post(f"/api/wishes/{wid}/claim", json={"claimer": claimer})
    assert r.status_code == 200, r.text


def get_wish(wid: int) -> dict:
    return client.get(f"/api/wishes/{wid}").json()


def done_ids() -> set[int]:
    return {row["id"] for row in client.get("/api/done").json()}


def raw_row(wid: int) -> dict:
    c = connect()
    row = dict(c.execute("SELECT * FROM wishes WHERE id=?", (wid,)).fetchone())
    c.close()
    return row


def test_preview_is_readonly_status_stays_claimed():
    wid = make_wish("预览不改状态")
    claim(wid)

    r = client.post(f"/api/wishes/{wid}/fulfill/preview",
                    json={"channel": "purchase", "reference": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "claimed"
    assert body["persisted"] is False

    # 草稿前后：状态不动、无 evidence、已完成无此编号、墙卡仍是待核销
    w = get_wish(wid)
    assert w["status"] == "claimed"
    assert w["evidence_view"] is None
    assert w["corner_badge"] == "待核销"
    assert wid not in done_ids()
    assert raw_row(wid)["evidence"] is None


def test_missing_fields_fails_without_fulfilled_shell():
    wid = make_wish("缺字段不留空壳")
    claim(wid)

    # 先拉草稿，再用缺字段提交 —— 两者叠加不得留下 fulfilled 空壳
    client.post(f"/api/wishes/{wid}/fulfill/preview",
                json={"channel": "purchase", "reference": ""})
    r = client.post(f"/api/wishes/{wid}/fulfill",
                    json={"channel": "purchase", "reference": "  "})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "incomplete_evidence"
    assert "reference" in detail["missing"]

    # 渠道与凭证都缺
    r2 = client.post(f"/api/wishes/{wid}/fulfill", json={})
    assert r2.status_code == 400
    assert set(r2.json()["detail"]["missing"]) == {"channel", "reference"}

    row = raw_row(wid)
    assert row["status"] == "claimed"          # 没被挪走
    assert row["evidence"] is None              # 无空壳残留
    assert row["fulfilled_at"] is None
    assert wid not in done_ids()
    w = get_wish(wid)
    assert w["corner_badge"] == "待核销"         # 墙按钮仍可核销
    assert w["evidence_view"] is None            # 详情举证区空白（仍是表单）


def test_success_pins_same_snapshot_in_three_places():
    wid = make_wish("成功三处同源")
    claim(wid, "bob")

    r = client.post(f"/api/wishes/{wid}/fulfill",
                    json={"channel": "handmade", "reference": "CRAFT-7", "note": "织好了"})
    assert r.status_code == 200, r.text
    snap = r.json()["snapshot"]
    assert snap["channel"] == "handmade"
    assert snap["reference"] == "CRAFT-7"
    assert snap["channel_label"] == "手工制作"

    # 墙卡
    w = get_wish(wid)
    assert w["status"] == "fulfilled"
    assert w["corner_tone"] == "done"
    assert "手工制作" in w["corner_badge"]
    assert w["evidence_summary"] == "手工制作 · CRAFT-7"

    # 详情举证区
    assert w["evidence_view"]["frozen"] is True
    assert w["evidence_view"]["channel"] == "handmade"
    assert w["evidence_view"]["reference"] == "CRAFT-7"

    # 已完成列表：同一份渠道+凭证
    assert wid in done_ids()
    card = next(c for c in client.get("/api/done").json() if c["id"] == wid)
    assert card["summary"] == "手工制作 · CRAFT-7"
    assert card["claimer"] == "bob"


def test_frozen_channel_cannot_change_after_success():
    wid = make_wish("钉住不可改")
    claim(wid)
    client.post(f"/api/wishes/{wid}/fulfill",
                json={"channel": "purchase", "reference": "ORDER-1"})

    # 改渠道再提交：409，快照纹丝不动
    r = client.post(f"/api/wishes/{wid}/fulfill",
                    json={"channel": "experience", "reference": "TICKET-9"})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "already_fulfilled"

    w = get_wish(wid)
    assert w["evidence_view"]["channel"] == "purchase"
    card = next(c for c in client.get("/api/done").json() if c["id"] == wid)
    assert card["summary"] == "实物购买 · ORDER-1"  # 禁止详情新渠道、已完成旧快照

    # 已冻结后预览也拒绝
    rp = client.post(f"/api/wishes/{wid}/fulfill/preview", json={"channel": "other"})
    assert rp.status_code == 409


def test_preview_requires_claimed():
    wid = make_wish("未认领不能预览")
    r = client.post(f"/api/wishes/{wid}/fulfill/preview", json={"channel": "purchase"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "need_claim"
    assert raw_row(wid)["status"] == "open"


def test_fulfilled_shell_rows_are_healed_and_hidden():
    """旧 bug 版本留下的 fulfilled+'{}' 空壳：启动自愈回 claimed，且不进已完成。"""
    wid = make_wish("历史空壳")
    claim(wid, "carol")
    c = connect()
    c.execute("UPDATE wishes SET status='fulfilled', evidence=? WHERE id=?",
              (json.dumps({}), wid))
    c.commit(); c.close()

    seed.init_db()  # 重放启动自愈

    row = raw_row(wid)
    assert row["status"] == "claimed"
    assert row["evidence"] is None
    assert wid not in done_ids()
    w = get_wish(wid)
    assert w["corner_badge"] == "待核销"
