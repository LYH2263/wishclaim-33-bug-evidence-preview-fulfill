"""核销举证包预览：claimed 状态下先看摘要+渠道枚举，不写库、不改 status。"""
from app.modules.fulfillment.channels import channel_catalog, channel_label
from app.modules.fulfillment.freeze import normalize_draft, validate_evidence


def preview_for(row: dict, body: dict | None) -> dict:
    """纯函数：根据愿望行和草稿生成预览。

    返回里显式回显当前 status，调用方据此断言预览前后状态不变。
    """
    draft = normalize_draft(body)
    verdict = validate_evidence(draft)

    label = channel_label(draft["channel"]) if draft["channel"] else None
    if label:
        summary = f"{label} · {draft['reference']}" if draft["reference"] else label
    elif draft["reference"]:
        summary = draft["reference"]
    else:
        summary = None

    return {
        "status": row.get("status"),
        "channels": channel_catalog(),
        "selected": draft["channel"] or None,
        "draft": {**draft, "channel_label": label},
        "summary": summary,
        "ready": verdict["ok"],
        "missing": verdict["missing"],
        "errors": verdict["errors"],
        "persisted": False,
    }
