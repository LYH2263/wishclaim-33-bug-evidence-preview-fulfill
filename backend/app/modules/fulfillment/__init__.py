"""核销举证包：渠道枚举（单一事实源）、预览、冻结写库、投影。"""
from app.modules.fulfillment.channels import CHANNELS, CHANNEL_KEYS, channel_catalog, channel_label
from app.modules.fulfillment.preview import preview_for
from app.modules.fulfillment.freeze import freeze_evidence, normalize_draft, validate_evidence
from app.modules.fulfillment.projection import (
    decorate,
    detail_panel,
    done_card,
    corner_badge,
    evidence_summary,
    evidence_view,
)
