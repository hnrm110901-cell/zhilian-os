"""
跨店洞察服务 (Cross-Store Insights)

基于多门店数据，自动识别：
1. 异常门店 — 今日指标偏离均值 > N 个标准差
2. 最佳实践 — 各指标 Top 门店及其特征
3. 同期对比 — 本周 vs 上周、本月 vs 上月
4. AI 洞察摘要 — 用 LLM 生成可读的跨店分析
"""
import os
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# 异常检测阈值（标准差倍数）
ANOMALY_THRESHOLD = float(os.getenv("CROSS_STORE_ANOMALY_THRESHOLD", "2.0"))


def _stats(values: List[float]) -> Dict[str, float]:
    """计算均值和标准差"""
    if not values:
        return {"mean": 0.0, "std": 0.0}
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return {"mean": mean, "std": variance ** 0.5}


class CrossStoreInsightsService:
    """跨店洞察服务"""

    # ------------------------------------------------------------------
    # 异常门店检测
    # ------------------------------------------------------------------

    def detect_anomalies(
        self,
        store_metrics: List[Dict[str, Any]],
        metric: str = "revenue",
        threshold: float = ANOMALY_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        检测指标异常的门店

        Args:
            store_metrics: [{"store_id": ..., "store_name": ..., "value": float, ...}]
            metric:        指标名称（用于日志）
            threshold:     异常阈值（标准差倍数）

        Returns:
            异常门店列表，含 z_score 和 direction（above/below）
        """
        values = [float(m.get("value", 0)) for m in store_metrics]
        s = _stats(values)
        mean, std = s["mean"], s["std"]

        anomalies = []
        for m in store_metrics:
            v = float(m.get("value", 0))
            z = (v - mean) / std if std > 0 else 0.0
            if abs(z) >= threshold:
                anomalies.append({
                    **m,
                    "metric": metric,
                    "z_score": round(z, 2),
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                    "direction": "above" if z > 0 else "below",
                })

        anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        return anomalies

    # ------------------------------------------------------------------
    # 最佳实践提取
    # ------------------------------------------------------------------

    def extract_best_practices(
        self,
        store_metrics: List[Dict[str, Any]],
        metric: str = "revenue",
        top_n: int = 3,
    ) -> Dict[str, Any]:
        """
        提取各指标 Top N 门店

        Returns:
            {
              "metric": ...,
              "top_stores": [...],
              "bottom_stores": [...],
              "spread": top_value / bottom_value,
            }
        """
        if not store_metrics:
            return {"metric": metric, "top_stores": [], "bottom_stores": [], "spread": 1.0}

        sorted_stores = sorted(store_metrics, key=lambda x: float(x.get("value", 0)), reverse=True)
        top = sorted_stores[:top_n]
        bottom = sorted_stores[-top_n:]

        top_val = float(top[0].get("value", 1)) if top else 1
        bot_val = float(bottom[-1].get("value", 1)) if bottom else 1
        spread = round(top_val / bot_val, 2) if bot_val > 0 else 0

        return {
            "metric": metric,
            "top_stores": top,
            "bottom_stores": bottom,
            "spread": spread,
            "mean": round(_stats([float(m.get("value", 0)) for m in store_metrics])["mean"], 2),
        }

    # ------------------------------------------------------------------
    # 同期对比
    # ------------------------------------------------------------------

    def period_comparison(
        self,
        current_metrics: List[Dict[str, Any]],
        previous_metrics: List[Dict[str, Any]],
        metric: str = "revenue",
    ) -> List[Dict[str, Any]]:
        """
        计算每家门店的同期变化率

        Args:
            current_metrics:  本期数据 [{"store_id": ..., "value": float}]
            previous_metrics: 上期数据 [{"store_id": ..., "value": float}]

        Returns:
            [{"store_id": ..., "current": ..., "previous": ..., "change_pct": ..., "trend": "up/down/flat"}]
        """
        prev_map = {m["store_id"]: float(m.get("value", 0)) for m in previous_metrics}
        result = []
        for m in current_metrics:
            sid = m["store_id"]
            curr = float(m.get("value", 0))
            prev = prev_map.get(sid, 0)
            if prev > 0:
                change_pct = round((curr - prev) / prev * 100, 1)
            else:
                change_pct = 0.0
            trend = "up" if change_pct > 1 else ("down" if change_pct < -1 else "flat")
            result.append({
                "store_id": sid,
                "store_name": m.get("store_name", sid),
                "metric": metric,
                "current": round(curr, 2),
                "previous": round(prev, 2),
                "change_pct": change_pct,
                "trend": trend,
            })
        result.sort(key=lambda x: x["change_pct"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # AI 洞察摘要
    # ------------------------------------------------------------------

    async def generate_insight_summary(
        self,
        anomalies: List[Dict[str, Any]],
        best_practices: Dict[str, Any],
        period_comparison: List[Dict[str, Any]],
        metric: str = "revenue",
        target_date: Optional[str] = None,
    ) -> str:
        """
        用 LLM 生成跨店洞察摘要

        降级：LLM 不可用时返回结构化文本摘要
        """
        target_date = target_date or date.today().isoformat()

        # 构建 prompt 上下文
        anomaly_text = ""
        if anomalies:
            lines = [f"- {a['store_name']}：{a['metric']} {a['direction']} 均值 {abs(a['z_score'])} 个标准差（值={a['value']}，均值={a['mean']}）" for a in anomalies[:5]]
            anomaly_text = "异常门店：\n" + "\n".join(lines)

        top_text = ""
        if best_practices.get("top_stores"):
            tops = best_practices["top_stores"]
            lines = [f"- {t.get('store_name', t['store_id'])}：{t.get('value', 0)}" for t in tops]
            top_text = f"Top 门店（{metric}）：\n" + "\n".join(lines)

        trend_text = ""
        if period_comparison:
            up = [p for p in period_comparison if p["trend"] == "up"][:3]
            down = [p for p in period_comparison if p["trend"] == "down"][:3]
            if up:
                trend_text += "增长最快：" + "、".join(f"{p['store_name']}(+{p['change_pct']}%)" for p in up) + "\n"
            if down:
                trend_text += "下滑最多：" + "、".join(f"{p['store_name']}({p['change_pct']}%)" for p in down)

        context = f"日期：{target_date}\n指标：{metric}\n\n{anomaly_text}\n\n{top_text}\n\n{trend_text}"

        try:
            from ..core.llm import get_llm_client
            llm = get_llm_client()
            if llm:
                prompt = (
                    f"你是智链OS的数据分析师。根据以下跨店数据，用2-3句话生成简洁的管理洞察，"
                    f"重点指出需要关注的门店和可借鉴的最佳实践：\n\n{context}"
                )
                response = await llm.agenerate([prompt])
                return response.generations[0][0].text.strip()
        except Exception as e:
            logger.warning("LLM 洞察生成失败，使用结构化摘要", error=str(e))

        # 降级：结构化文本
        parts = []
        if anomalies:
            parts.append(f"发现 {len(anomalies)} 家门店 {metric} 异常，其中 {anomalies[0].get('store_name', '')} 偏差最大（z={anomalies[0]['z_score']}）。")
        if best_practices.get("top_stores"):
            top = best_practices["top_stores"][0]
            parts.append(f"{metric} 最佳门店为 {top.get('store_name', top['store_id'])}（{top.get('value', 0)}），可作为标杆参考。")
        if period_comparison:
            up = [p for p in period_comparison if p["trend"] == "up"]
            down = [p for p in period_comparison if p["trend"] == "down"]
            if up or down:
                parts.append(f"同期对比：{len(up)} 家门店增长，{len(down)} 家门店下滑。")
        return " ".join(parts) if parts else "暂无显著跨店洞察。"


# Singleton
cross_store_insights_service = CrossStoreInsightsService()
