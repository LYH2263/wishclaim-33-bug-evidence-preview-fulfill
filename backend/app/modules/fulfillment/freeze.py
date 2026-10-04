"""冻结写库：核销举证的规范化、完整性校验、快照生成。

纯函数，不碰数据库 —— 由路由层在拿到 ok 快照后执行唯一一次写入。
校验失败时不产生快照，调用方必须保持 status=claimed。
"""
from datetime import datetime

from app.modules.fulfillment.channels import CHANNEL_KEYS, channel_label

SNAPSHOT_SCHEMA = "fulfillment-evidence-v1"


def normalize_draft(body: dict | None) -> dict:
    """把请求体收敛成 {channel, reference, note}，全部去首尾空白。"""
    body = body or {}

    def s(v):
        return v.strip() if isinstance(v, str) else ""

    return {"channel": s(body.get("channel")), "reference": s(body.get("reference")), "note": s(body.get("note"))}


def validate_evidence(draft: dict) -> dict:
    """完整性校验。channel 必须落在枚举内；reference 为必填非空白；note 选填。"""
    errors, missing = [], []
    channel = draft.get("channel") or ""
    reference = draft.get("reference") or ""
    if not channel:
        errors.append("channel_required"); missing.append("channel")
    elif channel not in CHANNEL_KEYS:
        errors.append("channel_invalid")
    if not reference:
        errors.append("reference_required"); missing.append("reference")
    return {"ok": not errors, "errors": errors, "missing": missing}


def is_frozen_snapshot(ev: dict | None) -> bool:
    """一份已冻结举证是否完整：schema 对、渠道在枚举内、凭证非空白。

    fulfilled 空壳（{}、缺 channel/reference）一律不算，投影与自愈共用这一把尺。
    """
    if not isinstance(ev, dict) or ev.get("schema") != SNAPSHOT_SCHEMA:
        return False
    channel = (ev.get("channel") or "").strip()
    reference = (ev.get("reference") or "").strip()
    return channel in CHANNEL_KEYS and bool(reference)


def freeze_evidence(status: str, claimer: str | None, body: dict | None, now: datetime) -> dict:
    """状态门 + 校验 + 快照。返回 {ok, reason, errors, missing, snapshot}。

    - 非 claimed 一律拒绝：fulfilled 为 already_fulfilled（钉住后不可再改），
      其余为 need_claim
    - 缺字段/空白拒绝，不返回 snapshot，调用方必须零写入、保持 claimed
    """
    if status == "fulfilled":
        return {"ok": False, "reason": "already_fulfilled", "errors": ["already_fulfilled"], "missing": [], "snapshot": None}
    if status != "claimed":
        return {"ok": False, "reason": "need_claim", "errors": ["need_claim"], "missing": [], "snapshot": None}

    draft = normalize_draft(body)
    verdict = validate_evidence(draft)
    if not verdict["ok"]:
        return {"ok": False, "reason": "incomplete_evidence", "errors": verdict["errors"],
                "missing": verdict["missing"], "snapshot": None}

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "channel": draft["channel"],
        "channel_label": channel_label(draft["channel"]),
        "reference": draft["reference"],
        "note": draft["note"],
        "claimer": claimer,
        "fulfilled_at": now.isoformat(),
    }
    return {"ok": True, "reason": "", "errors": [], "missing": [], "snapshot": snapshot}
