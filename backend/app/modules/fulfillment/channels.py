"""核销渠道枚举 —— 全栈唯一事实源。

前端不得硬编码渠道，一律通过 GET /api/fulfillment/channels 拉取本目录，
保证前后端渠道集合永远一致。key 入库、label 随快照钉住。
"""

CHANNELS = {
    "purchase": {"label": "实物购买", "hint": "订单号或购买凭证"},
    "handmade": {"label": "手工制作", "hint": "成品说明或制作记录"},
    "experience": {"label": "体验安排", "hint": "预约或订票凭证"},
    "other": {"label": "其他方式", "hint": "在备注中说明履约方式"},
}

CHANNEL_KEYS = tuple(CHANNELS.keys())


def channel_catalog() -> list[dict]:
    """供 /api/fulfillment/channels 与预览的渠道枚举区使用。"""
    return [{"key": k, "label": v["label"], "hint": v["hint"]} for k, v in CHANNELS.items()]


def channel_label(key: str | None) -> str | None:
    if not key:
        return None
    item = CHANNELS.get(key)
    return item["label"] if item else None
