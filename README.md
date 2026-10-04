# Wishclaim · 礼物愿望认领

发布 → 认领锁定（互斥+TTL）→ 预览举证包 → 提交完整举证核销/释放。

核销举证：
- `POST /api/wishes/{id}/fulfill/preview` 预览（摘要+渠道枚举），不写库、不改 `claimed`
- `POST /api/wishes/{id}/fulfill` 须提交枚举渠道 + 非空凭证号；缺字段/空白拒绝且保持 `claimed`
- 成功后写入冻结快照（`evidence` 列）并置 `fulfilled`；核销后禁止再改举证
- 渠道枚举唯一事实源：`GET /api/fulfillment/channels`（前端不得硬编码）
- 已完成列表摘要、详情举证区、墙角标由 `app/modules/fulfillment/projection.py` 同源投影；非 fulfilled 不进 `/api/done`

| 服务 | 端口 |
| --- | --- |
| 前端 | 5200 |
| API | 10200 |

```bash
docker compose up --build
pytest backend/app/tests
```

0-1：`wish_comment` / `secret_santa` / `price_cap`。
