"""
MVP 端点注册表 — v2.0 精简版

10个 MVP 功能对应的 API 端点清单（共 < 30 个端点）。
非 MVP 端点虽然保留代码，但在生产部署、监控和测试优先级中降级处理。

MVP 功能清单（来源：tasks/todo.md）：
  1. POS数据自动采集（天财商龙）
  2. 每日利润快报（含¥金额）
  3. 损耗Top5排名（含¥归因）
  4. 决策型企微推送（4时间点）
  5. 一键审批采购建议
  6. BOM配方管理（出纳录入）
  7. 成本率趋势图
  8. 异常告警推送（阈值可配置）
  9. 月度经营报告（PDF）
  10. 离线基础查询（断网可用）

使用方式：
  在主路由注册时使用 tags 区分 MVP/非MVP，
  本文件作为 MVP 端点的权威来源，CI 可用于生成最小化部署清单。
"""

from typing import Dict, List

# ════════════════════════════════════════════════════════════════════════════════
# MVP 端点清单（按 MVP 功能编号组织）
# ════════════════════════════════════════════════════════════════════════════════

MVP_ENDPOINTS: Dict[str, List[Dict]] = {
    # ── MVP-1: POS数据自动采集 ───────────────────────────────────────────────
    "mvp_1_pos_ingestion": [
        {
            "method": "POST",
            "path": "/api/v1/pos-webhook/{store_id}/order",
            "description": "接收 POS Webhook 推送的订单（美团/客如云/通用格式）",
        },
        {"method": "GET", "path": "/api/v1/pos-webhook/{store_id}/test", "description": "Webhook 连通性测试"},
        {"method": "POST", "path": "/api/v1/pos/{store_id}/pull", "description": "主动拉取天财商龙订单/菜品/库存数据"},
        {"method": "GET", "path": "/api/v1/pos/{store_id}/status", "description": "查看 POS 适配器连接状态"},
    ],
    # ── MVP-2: 每日利润快报 ──────────────────────────────────────────────────
    "mvp_2_daily_report": [
        {"method": "GET", "path": "/api/v1/daily-hub/report", "description": "获取门店今日利润快报（含¥金额）"},
        {"method": "GET", "path": "/api/v1/fct-public/dashboard", "description": "业财税资金一体化仪表盘（含 _yuan 字段）"},
        {"method": "GET", "path": "/api/v1/fct-public/cash-flow", "description": "现金流预测（含 _yuan 字段）"},
        {"method": "GET", "path": "/api/v1/fct-public/tax", "description": "月度税务测算（含 _yuan 字段）"},
    ],
    # ── MVP-3: 损耗Top5排名 ──────────────────────────────────────────────────
    "mvp_3_waste_ranking": [
        {"method": "GET", "path": "/api/v1/waste-events/top5", "description": "损耗Top5（按¥金额排序，含归因）"},
        {"method": "GET", "path": "/api/v1/waste-events/rate-summary", "description": "损耗率汇总（含环比）"},
        {"method": "GET", "path": "/api/v1/waste-events/bom-deviation", "description": "BOM偏差排名（识别超用食材）"},
    ],
    # ── MVP-4: 决策型企微推送 ────────────────────────────────────────────────
    "mvp_4_wechat_push": [
        {"method": "POST", "path": "/api/v1/wechat/push/morning", "description": "08:00 晨推 Top3 决策卡片"},
        {"method": "POST", "path": "/api/v1/wechat/push/noon-anomaly", "description": "12:00 午推异常告警（有异常才发）"},
        {"method": "POST", "path": "/api/v1/wechat/push/prebattle", "description": "17:30 战前推库存决策"},
        {"method": "POST", "path": "/api/v1/wechat/push/evening", "description": "20:30 晚推回顾+待审批数"},
    ],
    # ── MVP-5: 一键审批采购建议 ──────────────────────────────────────────────
    "mvp_5_approval": [
        {
            "method": "POST",
            "path": "/api/v1/wechat/approval-callback",
            "description": "企微审批回调（approve/reject/modify）→ 48h 效果跟踪",
        },
        {"method": "GET", "path": "/api/v1/decisions/pending", "description": "获取待审批决策列表"},
        {"method": "POST", "path": "/api/v1/decisions/{decision_id}/approve", "description": "批准决策"},
        {"method": "POST", "path": "/api/v1/decisions/{decision_id}/reject", "description": "拒绝决策"},
    ],
    # ── MVP-6: BOM配方管理 ───────────────────────────────────────────────────
    "mvp_6_bom": [
        {"method": "GET", "path": "/api/v1/bom/", "description": "获取 BOM 列表"},
        {"method": "POST", "path": "/api/v1/bom/", "description": "创建 BOM 版本"},
        {"method": "PUT", "path": "/api/v1/bom/{bom_id}", "description": "更新 BOM 版本"},
        {"method": "GET", "path": "/api/v1/bom/{bom_id}/cost-report", "description": "BOM 标准成本报告（含 food_cost%）"},
    ],
    # ── MVP-7: 成本率趋势图 ──────────────────────────────────────────────────
    "mvp_7_cost_trend": [
        {"method": "GET", "path": "/api/v1/hq/food-cost-variance", "description": "门店食材成本率差异分析（实际 vs 理论）"},
        {"method": "GET", "path": "/api/v1/hq/food-cost-ranking", "description": "总部跨店成本率排名"},
        {"method": "GET", "path": "/api/v1/hq/dashboard", "description": "总部经营仪表盘"},
    ],
    # ── MVP-8: 异常告警推送 ──────────────────────────────────────────────────
    "mvp_8_anomaly_alert": [
        {"method": "GET", "path": "/api/v1/notifications/", "description": "获取通知列表（含异常告警）"},
        {"method": "POST", "path": "/api/v1/notifications/thresholds", "description": "配置告警阈值（可调节）"},
        {"method": "GET", "path": "/api/v1/health", "description": "系统健康检查（运维监控用）"},
    ],
    # ── MVP-9: 月度经营报告 ──────────────────────────────────────────────────
    "mvp_9_monthly_report": [
        {"method": "GET", "path": "/api/v1/reports/monthly/{store_id}", "description": "生成月度经营报告（含案例叙事）"},
        {"method": "GET", "path": "/api/v1/reports/monthly/{store_id}/pdf", "description": "下载月度经营报告 PDF"},
    ],
    # ── MVP-10: 离线基础查询 ─────────────────────────────────────────────────
    "mvp_10_offline": [
        {"method": "GET", "path": "/api/v1/edge/revenue", "description": "离线查询营业额（断网时返回缓存）"},
        {"method": "GET", "path": "/api/v1/edge/inventory", "description": "离线查询库存快照（断网时返回缓存）"},
        {"method": "POST", "path": "/api/v1/edge/cache/revenue", "description": "更新营业额缓存（在线时主动写入）"},
        {"method": "POST", "path": "/api/v1/edge/cache/inventory", "description": "更新库存缓存（在线时主动写入）"},
    ],
}


def get_all_mvp_paths() -> List[str]:
    """返回所有 MVP 端点的路径列表"""
    paths = []
    for endpoints in MVP_ENDPOINTS.values():
        for ep in endpoints:
            paths.append(ep["path"])
    return paths


def get_mvp_endpoint_count() -> int:
    """返回 MVP 端点总数"""
    return sum(len(v) for v in MVP_ENDPOINTS.values())


def is_mvp_endpoint(path: str) -> bool:
    """判断某路径是否为 MVP 端点（模糊匹配，忽略路径参数）"""
    import re

    # 将 {param} 替换为通配符进行比较
    def normalize(p: str) -> str:
        return re.sub(r"\{[^}]+\}", "{}", p)

    normalized_path = normalize(path)
    for endpoints in MVP_ENDPOINTS.values():
        for ep in endpoints:
            if normalize(ep["path"]) == normalized_path:
                return True
    return False


# ════════════════════════════════════════════════════════════════════════════════
# 非 MVP 端点（保留代码，非优先）
# ════════════════════════════════════════════════════════════════════════════════
# 以下模块中的端点为非MVP范围（在 v2.0 阶段不列入主要维护/测试优先级）：
#   - neural.py, ontology.py, l3_knowledge.py, l4_reasoning.py, l5_action.py
#   - workflow.py, execution.py, forecasting.py, analytics.py
#   - embedding.py, vector_index.py, knowledge_rules.py
#   - banquet.py, banquet_lifecycle.py, supply_chain_router
#   - voice.py, voice_ws.py, hardware_integration.py
#   - federated_learning.py, model_marketplace.py, raas.py
#   - members.py, marketing_campaign.py, customer360.py
#   - meituan_queue.py, integrations.py, enterprise_integration.py
#   - i18n.py, industry_solutions.py, open_platform.py
#   等（共约 70+ 端点文件）
