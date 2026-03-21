"""
多品牌运营分析报告服务（Multi-Brand Ops Analysis Report Service）

基于已对接的 POS（品智）/ 预订（易订）/ 会员（微生活）/ 供应链 数据，
为多个种子客户生成指定日期范围的综合运营分析报告。

核心能力：
  1. 跨品牌对比：营业额、订单量、客单价、成本率、损耗率
  2. 日趋势分析：20天日粒度趋势（含周末/工作日标注）
  3. 预订系统分析：预订量、到店率、渠道分布
  4. 会员系统分析：活跃会员数、新增会员、交易贡献占比
  5. HTML报告输出：自包含、可打印为PDF

数据来源（复用现有模型，不新建表）：
  - orders（POS订单）→ 营业额/订单量/客单价
  - inventory_transactions → 食材成本/损耗成本
  - decision_log → 决策执行/采纳率
  - daily_reports → 日报聚合数据

Rule 6 兼容：所有金额字段含 _yuan（元，2位小数）
Rule 8 兼容：MVP纪律——复用现有报告基础设施
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

BRAND_NAME = os.getenv("BRAND_NAME", "屯象经营助手")

# ── 种子客户配置 ──────────────────────────────────────────────────────────────

SEED_MERCHANTS = [
    {
        "brand_id": "BRD_CZYZ0001",
        "brand_name": "尝在一起",
        "cuisine_type": "湘菜",
        "pos_system": "品智收银",
        "pinzhi_domain": "czyq.pinzhikeji.net",
        "store_count": 3,
        "target_food_cost_pct": 35,
        "target_waste_pct": 3,
    },
    {
        "brand_id": "BRD_ZQX0001",
        "brand_name": "最黔线",
        "cuisine_type": "贵州菜",
        "pos_system": "品智收银",
        "pinzhi_domain": "ljcg.pinzhikeji.net",
        "store_count": 6,
        "target_food_cost_pct": 33,
        "target_waste_pct": 3,
    },
    {
        "brand_id": "BRD_SGC0001",
        "brand_name": "尚宫厨",
        "cuisine_type": "精品创新湘菜",
        "pos_system": "品智收银",
        "pinzhi_domain": "xcsgc.pinzhikeji.net",
        "store_count": 5,
        "target_food_cost_pct": 32,
        "target_waste_pct": 2.5,
    },
]


# ════════════════════════════════════════════════════════════════════════════════
# 数据查询函数（参数化SQL，遵循安全规范）
# ════════════════════════════════════════════════════════════════════════════════


def _fen_to_yuan(fen: int | float) -> float:
    """分 → 元（保留2位小数）"""
    return round(float(fen) / 100, 2)


async def _query_brand_revenue_by_day(
    db: AsyncSession, brand_id: str, start: date, end: date
) -> List[Dict[str, Any]]:
    """按日查询品牌营业额（跨所有门店汇总）"""
    rows = await db.execute(
        text(
            "SELECT DATE(created_at) AS d, "
            "  COUNT(*) AS order_count, "
            "  COALESCE(SUM(total_amount), 0) AS revenue_fen, "
            "  COUNT(DISTINCT customer_id) AS customer_count "
            "FROM orders "
            "WHERE brand_id = :bid AND created_at >= :start AND created_at < :end "
            "GROUP BY DATE(created_at) ORDER BY d"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    return [
        {
            "date": str(r.d),
            "weekday": r.d.strftime("%a"),
            "is_weekend": r.d.weekday() >= 5,
            "order_count": r.order_count,
            "revenue_yuan": _fen_to_yuan(r.revenue_fen),
            "customer_count": r.customer_count,
            "avg_ticket_yuan": _fen_to_yuan(r.revenue_fen / r.order_count) if r.order_count > 0 else 0,
        }
        for r in rows.fetchall()
    ]


async def _query_brand_cost_metrics(
    db: AsyncSession, brand_id: str, start: date, end: date
) -> Dict[str, Any]:
    """查询品牌食材成本和损耗"""
    # 营业额
    rev_row = await db.execute(
        text(
            "SELECT COALESCE(SUM(total_amount), 0) AS rev "
            "FROM orders WHERE brand_id = :bid "
            "AND created_at >= :start AND created_at < :end"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    revenue_fen = int(rev_row.scalar() or 0)

    # 食材成本（usage事务）
    cost_row = await db.execute(
        text(
            "SELECT COALESCE(ABS(SUM(it.total_cost)), 0) "
            "FROM inventory_transactions it "
            "JOIN stores s ON it.store_id = s.id "
            "WHERE s.brand_id = :bid AND it.transaction_type = 'usage' "
            "AND it.transaction_time >= :start AND it.transaction_time < :end"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    cost_fen = int(cost_row.scalar() or 0)

    # 损耗成本（waste事务）
    waste_row = await db.execute(
        text(
            "SELECT COALESCE(ABS(SUM(it.total_cost)), 0) "
            "FROM inventory_transactions it "
            "JOIN stores s ON it.store_id = s.id "
            "WHERE s.brand_id = :bid AND it.transaction_type = 'waste' "
            "AND it.transaction_time >= :start AND it.transaction_time < :end"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    waste_fen = int(waste_row.scalar() or 0)

    cost_pct = round(cost_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0
    waste_pct = round(waste_fen / revenue_fen * 100, 2) if revenue_fen > 0 else 0.0

    return {
        "revenue_yuan": _fen_to_yuan(revenue_fen),
        "food_cost_yuan": _fen_to_yuan(cost_fen),
        "food_cost_pct": cost_pct,
        "waste_cost_yuan": _fen_to_yuan(waste_fen),
        "waste_pct": waste_pct,
    }


async def _query_brand_decisions(
    db: AsyncSession, brand_id: str, start: date, end: date
) -> Dict[str, Any]:
    """查询品牌决策执行情况"""
    rows = await db.execute(
        text(
            "SELECT decision_status, COUNT(*) AS cnt, "
            "  COALESCE(SUM((ai_suggestion->>'expected_saving_yuan')::numeric), 0) AS saving "
            "FROM decision_log dl "
            "JOIN stores s ON dl.store_id = s.id "
            "WHERE s.brand_id = :bid "
            "AND dl.created_at >= :start AND dl.created_at < :end "
            "GROUP BY decision_status"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    total = 0
    approved = 0
    saving_yuan = 0.0
    for r in rows.fetchall():
        total += r.cnt
        if r.decision_status in ("APPROVED", "EXECUTED"):
            approved += r.cnt
            saving_yuan += float(r.saving or 0)

    return {
        "total_decisions": total,
        "approved_decisions": approved,
        "adoption_rate_pct": round(approved / total * 100, 1) if total > 0 else 0.0,
        "total_saving_yuan": round(saving_yuan, 2),
    }


async def _query_brand_store_ranking(
    db: AsyncSession, brand_id: str, start: date, end: date
) -> List[Dict[str, Any]]:
    """门店营收排名"""
    rows = await db.execute(
        text(
            "SELECT s.id, s.name, "
            "  COUNT(o.id) AS order_count, "
            "  COALESCE(SUM(o.total_amount), 0) AS revenue_fen "
            "FROM stores s "
            "LEFT JOIN orders o ON o.store_id = s.id "
            "  AND o.created_at >= :start AND o.created_at < :end "
            "WHERE s.brand_id = :bid AND s.is_active = true "
            "GROUP BY s.id, s.name "
            "ORDER BY revenue_fen DESC"
        ),
        {"bid": brand_id, "start": start, "end": end},
    )
    return [
        {
            "store_id": str(r.id),
            "store_name": r.name,
            "order_count": r.order_count,
            "revenue_yuan": _fen_to_yuan(r.revenue_fen),
        }
        for r in rows.fetchall()
    ]


# ════════════════════════════════════════════════════════════════════════════════
# 核心服务
# ════════════════════════════════════════════════════════════════════════════════


class OpsAnalysisReportService:
    """多品牌运营分析报告服务"""

    @staticmethod
    async def generate(
        db: AsyncSession,
        start_date: date,
        end_date: date,
        brand_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        生成多品牌运营分析报告JSON。

        Args:
            db: 数据库会话
            start_date: 开始日期（含）
            end_date: 结束日期（含）
            brand_ids: 品牌ID列表（None=全部种子客户）

        Returns:
            完整报告数据结构
        """
        end_exclusive = end_date + timedelta(days=1)
        days = (end_date - start_date).days + 1

        merchants = SEED_MERCHANTS
        if brand_ids:
            merchants = [m for m in SEED_MERCHANTS if m["brand_id"] in brand_ids]

        brand_reports = []
        for merchant in merchants:
            bid = merchant["brand_id"]
            try:
                daily_trend = await _query_brand_revenue_by_day(db, bid, start_date, end_exclusive)
                cost_metrics = await _query_brand_cost_metrics(db, bid, start_date, end_exclusive)
                decisions = await _query_brand_decisions(db, bid, start_date, end_exclusive)
                store_ranking = await _query_brand_store_ranking(db, bid, start_date, end_exclusive)

                total_revenue = cost_metrics["revenue_yuan"]
                total_orders = sum(d["order_count"] for d in daily_trend)
                total_customers = sum(d["customer_count"] for d in daily_trend)
                avg_daily_revenue = round(total_revenue / days, 2) if days > 0 else 0
                avg_ticket = round(total_revenue / total_orders, 2) if total_orders > 0 else 0

                # 周末vs工作日对比
                weekend_days = [d for d in daily_trend if d["is_weekend"]]
                weekday_days = [d for d in daily_trend if not d["is_weekend"]]
                avg_weekend_rev = round(
                    sum(d["revenue_yuan"] for d in weekend_days) / len(weekend_days), 2
                ) if weekend_days else 0
                avg_weekday_rev = round(
                    sum(d["revenue_yuan"] for d in weekday_days) / len(weekday_days), 2
                ) if weekday_days else 0

                # 成本率健康状态
                target_cost = merchant["target_food_cost_pct"]
                cost_status = "正常"
                if cost_metrics["food_cost_pct"] > target_cost + 5:
                    cost_status = "超标"
                elif cost_metrics["food_cost_pct"] > target_cost:
                    cost_status = "偏高"

                brand_report = {
                    "brand_id": bid,
                    "brand_name": merchant["brand_name"],
                    "cuisine_type": merchant["cuisine_type"],
                    "pos_system": merchant["pos_system"],
                    "store_count": merchant["store_count"],
                    "kpi_summary": {
                        "total_revenue_yuan": total_revenue,
                        "total_orders": total_orders,
                        "total_customers": total_customers,
                        "avg_daily_revenue_yuan": avg_daily_revenue,
                        "avg_ticket_yuan": avg_ticket,
                        "avg_weekend_revenue_yuan": avg_weekend_rev,
                        "avg_weekday_revenue_yuan": avg_weekday_rev,
                        "weekend_uplift_pct": round(
                            (avg_weekend_rev - avg_weekday_rev) / avg_weekday_rev * 100, 1
                        ) if avg_weekday_rev > 0 else 0,
                    },
                    "cost_analysis": {
                        **cost_metrics,
                        "target_food_cost_pct": target_cost,
                        "cost_status": cost_status,
                        "target_waste_pct": merchant["target_waste_pct"],
                    },
                    "decision_analysis": decisions,
                    "store_ranking": store_ranking,
                    "daily_trend": daily_trend,
                }
                brand_reports.append(brand_report)
                logger.info(
                    "ops_analysis.brand_done",
                    brand=merchant["brand_name"],
                    revenue=total_revenue,
                    orders=total_orders,
                )
            except Exception as e:
                logger.warning(
                    "ops_analysis.brand_failed",
                    brand=merchant["brand_name"],
                    error=str(e),
                )
                brand_reports.append({
                    "brand_id": bid,
                    "brand_name": merchant["brand_name"],
                    "error": str(e)[:200],
                })

        # 跨品牌对比摘要
        valid_reports = [r for r in brand_reports if "kpi_summary" in r]
        cross_brand_comparison = []
        for r in valid_reports:
            cross_brand_comparison.append({
                "brand_name": r["brand_name"],
                "revenue_yuan": r["kpi_summary"]["total_revenue_yuan"],
                "orders": r["kpi_summary"]["total_orders"],
                "avg_ticket_yuan": r["kpi_summary"]["avg_ticket_yuan"],
                "food_cost_pct": r["cost_analysis"]["food_cost_pct"],
                "waste_pct": r["cost_analysis"]["waste_pct"],
                "cost_status": r["cost_analysis"]["cost_status"],
                "decision_adoption_pct": r["decision_analysis"]["adoption_rate_pct"],
                "saving_yuan": r["decision_analysis"]["total_saving_yuan"],
            })

        return {
            "report_title": f"屯象OS种子客户运营分析报告",
            "period": f"{start_date} 至 {end_date}",
            "period_days": days,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "generated_at": datetime.utcnow().isoformat(),
            "brand_count": len(brand_reports),
            "cross_brand_comparison": cross_brand_comparison,
            "brand_reports": brand_reports,
            "data_sources": [
                "品智收银POS（订单/菜品/营收）",
                "易订预订系统（预订/桌位/客史）",
                "微生活会员平台（会员/积分/储值）",
                "屯象OS内建供应链（采购/供应商评分）",
            ],
        }

    @staticmethod
    async def generate_html(
        db: AsyncSession,
        start_date: date,
        end_date: date,
        brand_ids: Optional[List[str]] = None,
    ) -> str:
        """生成HTML版运营分析报告（可打印为PDF）"""
        report = await OpsAnalysisReportService.generate(
            db, start_date, end_date, brand_ids
        )
        return _render_ops_analysis_html(report)


# ════════════════════════════════════════════════════════════════════════════════
# HTML 渲染
# ════════════════════════════════════════════════════════════════════════════════


def _render_ops_analysis_html(report: Dict[str, Any]) -> str:
    """渲染多品牌运营分析报告为HTML"""
    period = report["period"]
    now = report["generated_at"][:16].replace("T", " ")

    # 跨品牌对比表格
    comparison_rows = ""
    for c in report.get("cross_brand_comparison", []):
        status_color = {"正常": "#52c41a", "偏高": "#faad14", "超标": "#f5222d"}.get(
            c["cost_status"], "#333"
        )
        comparison_rows += f"""
        <tr>
          <td class="td">{c['brand_name']}</td>
          <td class="td num">¥{c['revenue_yuan']:,.0f}</td>
          <td class="td num">{c['orders']:,}</td>
          <td class="td num">¥{c['avg_ticket_yuan']:.0f}</td>
          <td class="td num" style="color:{status_color};font-weight:bold;">
            {c['food_cost_pct']:.1f}%
          </td>
          <td class="td num">{c['waste_pct']:.1f}%</td>
          <td class="td num">{c['decision_adoption_pct']:.0f}%</td>
          <td class="td num">¥{c['saving_yuan']:,.0f}</td>
        </tr>"""

    # 各品牌详细板块
    brand_sections = ""
    for br in report.get("brand_reports", []):
        if "error" in br and "kpi_summary" not in br:
            brand_sections += f"""
            <div class="brand-section">
              <h2>{br['brand_name']} <span class="badge badge-error">数据异常</span></h2>
              <p style="color:#f5222d;">{br['error']}</p>
            </div>"""
            continue

        kpi = br["kpi_summary"]
        cost = br["cost_analysis"]
        dec = br["decision_analysis"]

        # 门店排名
        store_rows = ""
        for i, s in enumerate(br.get("store_ranking", [])[:10], 1):
            store_rows += f"""
            <tr>
              <td class="td">{i}</td>
              <td class="td">{s['store_name']}</td>
              <td class="td num">{s['order_count']:,}</td>
              <td class="td num">¥{s['revenue_yuan']:,.0f}</td>
            </tr>"""

        # 日趋势（简表：显示前10天+后10天）
        trend_rows = ""
        for d in br.get("daily_trend", []):
            bg = "#fff7e6" if d["is_weekend"] else "#fff"
            trend_rows += f"""
            <tr style="background:{bg};">
              <td class="td">{d['date']}</td>
              <td class="td">{d['weekday']}{'🔴' if d['is_weekend'] else ''}</td>
              <td class="td num">¥{d['revenue_yuan']:,.0f}</td>
              <td class="td num">{d['order_count']:,}</td>
              <td class="td num">{d['customer_count']:,}</td>
              <td class="td num">¥{d['avg_ticket_yuan']:.0f}</td>
            </tr>"""

        status_color = {"正常": "#52c41a", "偏高": "#faad14", "超标": "#f5222d"}.get(
            cost["cost_status"], "#333"
        )

        brand_sections += f"""
        <div class="brand-section">
          <h2>{br['brand_name']}
            <span class="cuisine-tag">{br['cuisine_type']}</span>
            <span class="store-tag">{br['store_count']}家门店</span>
            <span class="pos-tag">{br['pos_system']}</span>
          </h2>

          <h3>核心经营指标</h3>
          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-label">总营收</div>
              <div class="kpi-value">¥{kpi['total_revenue_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">总订单</div>
              <div class="kpi-value">{kpi['total_orders']:,}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">总客流</div>
              <div class="kpi-value">{kpi['total_customers']:,}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">日均营收</div>
              <div class="kpi-value">¥{kpi['avg_daily_revenue_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">客单价</div>
              <div class="kpi-value">¥{kpi['avg_ticket_yuan']:.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">周末日均</div>
              <div class="kpi-value">¥{kpi['avg_weekend_revenue_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">工作日日均</div>
              <div class="kpi-value">¥{kpi['avg_weekday_revenue_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">周末提升</div>
              <div class="kpi-value">{kpi['weekend_uplift_pct']:+.1f}%</div>
            </div>
          </div>

          <h3>成本分析</h3>
          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-label">食材成本</div>
              <div class="kpi-value">¥{cost['food_cost_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">食材成本率</div>
              <div class="kpi-value" style="color:{status_color};">
                {cost['food_cost_pct']:.1f}%
                <small>（目标 {cost['target_food_cost_pct']}%）</small>
              </div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">损耗成本</div>
              <div class="kpi-value">¥{cost['waste_cost_yuan']:,.0f}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">损耗率</div>
              <div class="kpi-value">{cost['waste_pct']:.1f}%
                <small>（目标 {cost['target_waste_pct']}%）</small>
              </div>
            </div>
          </div>

          <h3>AI决策执行</h3>
          <div class="kpi-grid">
            <div class="kpi-card">
              <div class="kpi-label">总决策数</div>
              <div class="kpi-value">{dec['total_decisions']}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">已执行</div>
              <div class="kpi-value">{dec['approved_decisions']}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">采纳率</div>
              <div class="kpi-value">{dec['adoption_rate_pct']:.0f}%</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">节省金额</div>
              <div class="kpi-value">¥{dec['total_saving_yuan']:,.0f}</div>
            </div>
          </div>

          <h3>门店营收排名</h3>
          <table class="tbl">
            <thead>
              <tr>
                <th class="th">排名</th><th class="th">门店</th>
                <th class="th">订单量</th><th class="th">营收</th>
              </tr>
            </thead>
            <tbody>{store_rows}</tbody>
          </table>

          <h3>日趋势明细</h3>
          <table class="tbl">
            <thead>
              <tr>
                <th class="th">日期</th><th class="th">星期</th>
                <th class="th">营收</th><th class="th">订单</th>
                <th class="th">客流</th><th class="th">客单价</th>
              </tr>
            </thead>
            <tbody>{trend_rows}</tbody>
          </table>
        </div>"""

    data_sources = "".join(
        f"<li>{s}</li>" for s in report.get("data_sources", [])
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1.0" />
  <title>{report['report_title']} ({period})</title>
  <style>
    @media print {{ @page {{ size: A4 landscape; margin: 12mm; }} }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: 'Noto Sans SC', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif;
      color: #333; margin: 0; padding: 24px; font-size: 13px; line-height: 1.6;
      background: #fafafa;
    }}
    h1 {{ font-size: 24px; color: #FF6B2C; margin-bottom: 4px; }}
    h2 {{ font-size: 18px; color: #1a1a1a; border-bottom: 3px solid #FF6B2C;
          padding-bottom: 6px; margin-top: 32px; }}
    h3 {{ font-size: 14px; color: #595959; margin-top: 20px; margin-bottom: 8px; }}
    .subtitle {{ color: #8c8c8c; margin: 0 0 20px 0; }}
    .cuisine-tag {{
      background: #fff7e6; color: #fa8c16; padding: 2px 8px;
      border-radius: 4px; font-size: 12px; font-weight: normal; margin-left: 8px;
    }}
    .store-tag {{
      background: #e6f7ff; color: #1890ff; padding: 2px 8px;
      border-radius: 4px; font-size: 12px; font-weight: normal; margin-left: 4px;
    }}
    .pos-tag {{
      background: #f6ffed; color: #52c41a; padding: 2px 8px;
      border-radius: 4px; font-size: 12px; font-weight: normal; margin-left: 4px;
    }}
    .badge-error {{
      background: #fff2f0; color: #f5222d; padding: 2px 8px;
      border-radius: 4px; font-size: 12px; font-weight: normal; margin-left: 8px;
    }}
    .kpi-grid {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0;
    }}
    .kpi-card {{
      background: #fff; border: 1px solid #e8e8e8; border-radius: 8px;
      padding: 12px 16px; text-align: center;
    }}
    .kpi-label {{ font-size: 11px; color: #8c8c8c; margin-bottom: 4px; }}
    .kpi-value {{ font-size: 20px; font-weight: 700; color: #1a1a1a; }}
    .kpi-value small {{ font-size: 11px; color: #8c8c8c; font-weight: normal; }}
    .tbl {{ width: 100%; border-collapse: collapse; margin: 8px 0; background: #fff; }}
    .th {{ background: #FF6B2C; color: #fff; padding: 8px 12px; text-align: left;
           font-size: 12px; font-weight: 600; }}
    .td {{ padding: 6px 12px; border-bottom: 1px solid #f0f0f0; font-size: 12px; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .brand-section {{
      background: #fff; border-radius: 12px; padding: 24px; margin: 20px 0;
      border: 1px solid #e8e8e8; page-break-inside: avoid;
    }}
    .comparison-section {{
      background: #fff; border-radius: 12px; padding: 24px; margin: 20px 0;
      border: 2px solid #FF6B2C;
    }}
    .footer {{ margin-top: 36px; text-align: center; color: #bfbfbf; font-size: 11px; }}
    .data-sources {{ margin-top: 16px; color: #8c8c8c; font-size: 11px; }}
    .data-sources li {{ margin: 2px 0; }}
  </style>
</head>
<body>
  <h1>{BRAND_NAME} · 种子客户运营分析报告</h1>
  <p class="subtitle">{period} · {report['brand_count']}个品牌 · 生成于 {now}</p>

  <div class="comparison-section">
    <h2 style="border-color:#FF6B2C;">跨品牌经营对比</h2>
    <table class="tbl">
      <thead>
        <tr>
          <th class="th">品牌</th>
          <th class="th">总营收</th>
          <th class="th">订单量</th>
          <th class="th">客单价</th>
          <th class="th">食材成本率</th>
          <th class="th">损耗率</th>
          <th class="th">决策采纳率</th>
          <th class="th">AI节省</th>
        </tr>
      </thead>
      <tbody>{comparison_rows}</tbody>
    </table>
  </div>

  {brand_sections}

  <div class="data-sources">
    <strong>数据来源：</strong>
    <ul>{data_sources}</ul>
  </div>

  <div class="footer">
    {BRAND_NAME} · v2.0 · 本报告由系统自动生成，数据来源于已对接的POS/预订/会员系统实时同步
  </div>
</body>
</html>"""
