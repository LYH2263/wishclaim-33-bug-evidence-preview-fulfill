"""核销举证投影：同一份冻结快照向三个读场景投影。

- done_card   已完成列表的一行摘要
- detail_panel 详情页举证区（完整快照）
- corner_badge 愿望墙卡片的墙角标
三者必须同源，禁止各写一套文案。
"""
import json

from app.modules.fulfillment.channels import channel_label


def parse_evidence(raw) -> dict | None:
    """从行数据取出已冻结的举证快照；未核销或脏数据一律 None。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        ev = raw
    else:
        try:
            ev = json.loads(raw)
        except (TypeError, ValueError):
            return None
    if not isinstance(ev, dict):
        return None
    return ev


def _label(ev: dict) -> str:
    """快照优先：钉住的 label 不随后续枚举改动而变。"""
    return ev.get("channel_label") or channel_label(ev.get("channel")) or ev["channel"]


def evidence_summary(ev: dict | None) -> str | None:
    """一行摘要：渠道 · 凭证号。"""
    if not ev:
        return None
    ref = (ev.get("reference") or "").strip()
    return f"{_label(ev)} · {ref}" if ref else _label(ev)


def evidence_view(ev: dict | None) -> dict | None:
    """详情举证区视图：完整、只读。"""
    if not ev:
        return None
    return {
        "channel": ev.get("channel"),
        "channel_label": _label(ev),
        "reference": ev.get("reference", ""),
        "note": ev.get("note", ""),
        "fulfilled_at": ev.get("fulfilled_at"),
        "frozen": True,
    }


def done_card(row: dict) -> dict | None:
    """已完成列表投影：只暴露摘要。

    status=fulfilled 但没有完整冻结快照的脏行返回 None，
    由路由层丢弃——已完成列表禁止渠道空/凭证空的行。
    """
    ev = parse_evidence(row.get("evidence"))
    if not ev or not (ev.get("channel") and str(ev.get("reference") or "").strip()):
        return None
    return {
        "id": row["id"],
        "title": row.get("title"),
        "claimer": row.get("claimer"),
        "status": "fulfilled",
        "summary": evidence_summary(ev),
        "fulfilled_at": (ev or {}).get("fulfilled_at") or row.get("fulfilled_at"),
    }


def detail_panel(row: dict) -> dict:
    """详情举证区投影。未核销时没有举证区。"""
    ev = parse_evidence(row.get("evidence"))
    view = evidence_view(ev)
    return {
        "status": row.get("status"),
        "frozen": view is not None,
        "summary": evidence_summary(ev),
        "evidence": view,
    }


def corner_badge(row: dict) -> dict:
    """愿望墙墙角标。fulfilled 钉渠道摘要；claimed 提示待核销；其余 None。"""
    if row.get("status") == "fulfilled":
        ev = parse_evidence(row.get("evidence"))
        text = f"✓ 已核销 · {_label(ev)}" if ev else "✓ 已核销"
        return {"text": text, "tone": "done"}
    if row.get("status") == "claimed":
        return {"text": "待核销", "tone": "pending"}
    return {"text": None, "tone": None}


def decorate(row: dict) -> dict:
    """给愿望行挂投影字段，供列表/详情接口直接使用。"""
    out = dict(row)
    ev = parse_evidence(row.get("evidence"))
    out["evidence_summary"] = evidence_summary(ev)
    out["evidence_view"] = evidence_view(ev)
    badge = corner_badge(row)
    out["corner_badge"] = badge["text"]
    out["corner_tone"] = badge["tone"]
    return out
