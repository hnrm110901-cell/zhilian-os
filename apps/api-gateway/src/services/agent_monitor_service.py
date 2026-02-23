"""
Agent决策监控服务
用于监控和分析Agent的决策质量和性能
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import os
import structlog

logger = structlog.get_logger()


class AgentMonitorService:
    """
    Agent监控服务

    功能:
    - 记录Agent决策
    - 统计性能指标
    - 分析决策质量
    - 生成监控报告
    """

    def __init__(self):
        # 内存存储 (生产环境应使用数据库或时序数据库)
        self.decisions = []
        self.metrics_cache = {}

    async def log_agent_decision(
        self,
        agent_type: str,
        method_name: str,
        store_id: str,
        request_params: Dict[str, Any],
        response_data: Dict[str, Any],
        execution_time_ms: float,
        success: bool,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        记录Agent决策

        Args:
            agent_type: Agent类型 (decision/schedule/inventory/order/kpi)
            method_name: 方法名
            store_id: 门店ID
            request_params: 请求参数
            response_data: 响应数据
            execution_time_ms: 执行时间(毫秒)
            success: 是否成功
            error: 错误信息

        Returns:
            记录结果
        """
        try:
            decision_record = {
                "id": f"{agent_type}_{datetime.now().timestamp()}",
                "agent_type": agent_type,
                "method_name": method_name,
                "store_id": store_id,
                "request_params": request_params,
                "response_data": response_data,
                "execution_time_ms": execution_time_ms,
                "success": success,
                "error": error,
                "timestamp": datetime.now(),
                "context_used": response_data.get("context_used", 0) if success else 0,
                "rag_enabled": response_data.get("context_used", 0) > 0 if success else False
            }

            self.decisions.append(decision_record)

            # 清理旧数据 (保留最近24小时)
            cutoff_time = datetime.now() - timedelta(hours=int(os.getenv("AGENT_MONITOR_RETENTION_HOURS", "24")))
            self.decisions = [
                d for d in self.decisions
                if d["timestamp"] > cutoff_time
            ]

            logger.info(
                "Agent decision logged",
                agent_type=agent_type,
                method_name=method_name,
                execution_time_ms=execution_time_ms,
                success=success
            )

            return {
                "success": True,
                "decision_id": decision_record["id"]
            }

        except Exception as e:
            logger.error(
                "Failed to log agent decision",
                agent_type=agent_type,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def get_agent_metrics(
        self,
        agent_type: Optional[str] = None,
        time_range: str = "1h"
    ) -> Dict[str, Any]:
        """
        获取Agent指标

        Args:
            agent_type: Agent类型 (None表示所有Agent)
            time_range: 时间范围 (1h/6h/24h)

        Returns:
            Agent指标
        """
        try:
            # 解析时间范围
            time_ranges = {
                "1h": timedelta(hours=1),
                "6h": timedelta(hours=6),
                "24h": timedelta(hours=24)
            }
            delta = time_ranges.get(time_range, timedelta(hours=1))
            cutoff_time = datetime.now() - delta

            # 过滤决策记录
            filtered_decisions = [
                d for d in self.decisions
                if d["timestamp"] > cutoff_time
                and (agent_type is None or d["agent_type"] == agent_type)
            ]

            if not filtered_decisions:
                return {
                    "success": True,
                    "metrics": {
                        "total_decisions": 0,
                        "success_rate": 0,
                        "avg_execution_time_ms": 0,
                        "rag_usage_rate": 0
                    }
                }

            # 计算指标
            total_decisions = len(filtered_decisions)
            successful_decisions = sum(1 for d in filtered_decisions if d["success"])
            total_execution_time = sum(d["execution_time_ms"] for d in filtered_decisions)
            rag_enabled_decisions = sum(1 for d in filtered_decisions if d["rag_enabled"])

            # 按Agent类型分组
            by_agent_type = defaultdict(list)
            for d in filtered_decisions:
                by_agent_type[d["agent_type"]].append(d)

            agent_breakdown = {}
            for atype, decisions in by_agent_type.items():
                agent_breakdown[atype] = {
                    "total": len(decisions),
                    "success_rate": sum(1 for d in decisions if d["success"]) / len(decisions) * 100,
                    "avg_execution_time_ms": sum(d["execution_time_ms"] for d in decisions) / len(decisions)
                }

            # 按方法分组
            by_method = defaultdict(list)
            for d in filtered_decisions:
                by_method[d["method_name"]].append(d)

            method_breakdown = {}
            for method, decisions in by_method.items():
                method_breakdown[method] = {
                    "total": len(decisions),
                    "success_rate": sum(1 for d in decisions if d["success"]) / len(decisions) * 100,
                    "avg_execution_time_ms": sum(d["execution_time_ms"] for d in decisions) / len(decisions)
                }

            metrics = {
                "total_decisions": total_decisions,
                "success_rate": (successful_decisions / total_decisions * 100) if total_decisions > 0 else 0,
                "avg_execution_time_ms": (total_execution_time / total_decisions) if total_decisions > 0 else 0,
                "rag_usage_rate": (rag_enabled_decisions / total_decisions * 100) if total_decisions > 0 else 0,
                "by_agent_type": agent_breakdown,
                "by_method": method_breakdown,
                "time_range": time_range,
                "period_start": cutoff_time.isoformat(),
                "period_end": datetime.now().isoformat()
            }

            logger.info(
                "Agent metrics retrieved",
                agent_type=agent_type,
                time_range=time_range,
                total_decisions=total_decisions
            )

            return {
                "success": True,
                "metrics": metrics
            }

        except Exception as e:
            logger.error(
                "Failed to get agent metrics",
                agent_type=agent_type,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def analyze_decision_quality(
        self,
        agent_type: str,
        time_range: str = "24h"
    ) -> Dict[str, Any]:
        """
        分析决策质量

        Args:
            agent_type: Agent类型
            time_range: 时间范围

        Returns:
            决策质量分析
        """
        try:
            # 获取指标
            metrics_result = await self.get_agent_metrics(agent_type, time_range)
            if not metrics_result["success"]:
                return metrics_result

            metrics = metrics_result["metrics"]

            # 质量评分 (0-100)
            quality_score = 0

            # 成功率权重: 40%
            success_rate = metrics.get("success_rate", 0)
            quality_score += (success_rate / 100) * float(os.getenv("AGENT_SCORE_SUCCESS_WEIGHT", "40"))

            # 响应时间权重: 30% (目标<1000ms)
            avg_time = metrics.get("avg_execution_time_ms", 0)
            time_score = max(0, 100 - (avg_time / 10))  # 每10ms扣1分
            quality_score += (time_score / 100) * float(os.getenv("AGENT_SCORE_TIME_WEIGHT", "30"))

            # RAG使用率权重: 30% (目标>80%)
            rag_rate = metrics.get("rag_usage_rate", 0)
            quality_score += (rag_rate / 100) * float(os.getenv("AGENT_SCORE_RAG_WEIGHT", "30"))

            # 质量等级
            if quality_score >= float(os.getenv("AGENT_QUALITY_EXCELLENT", "90")):
                quality_level = "优秀"
            elif quality_score >= float(os.getenv("AGENT_QUALITY_GOOD", "75")):
                quality_level = "良好"
            elif quality_score >= float(os.getenv("AGENT_QUALITY_PASS", "60")):
                quality_level = "及格"
            else:
                quality_level = "待改进"

            # 改进建议
            recommendations = []
            if success_rate < 95:
                recommendations.append(f"成功率偏低({success_rate:.1f}%)，需要优化错误处理")
            if avg_time > 1000:
                recommendations.append(f"响应时间偏慢({avg_time:.0f}ms)，需要性能优化")
            if rag_rate < 80:
                recommendations.append(f"RAG使用率偏低({rag_rate:.1f}%)，建议增加上下文检索")

            analysis = {
                "agent_type": agent_type,
                "quality_score": round(quality_score, 2),
                "quality_level": quality_level,
                "metrics": metrics,
                "recommendations": recommendations,
                "timestamp": datetime.now().isoformat()
            }

            logger.info(
                "Decision quality analyzed",
                agent_type=agent_type,
                quality_score=quality_score,
                quality_level=quality_level
            )

            return {
                "success": True,
                "analysis": analysis
            }

        except Exception as e:
            logger.error(
                "Failed to analyze decision quality",
                agent_type=agent_type,
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }

    async def get_realtime_stats(self) -> Dict[str, Any]:
        """
        获取实时统计

        Returns:
            实时统计数据
        """
        try:
            # 最近1小时的数据
            one_hour_ago = datetime.now() - timedelta(hours=int(os.getenv("AGENT_STATS_WINDOW_HOURS", "1")))
            recent_decisions = [
                d for d in self.decisions
                if d["timestamp"] > one_hour_ago
            ]

            # 最近5分钟的数据
            five_min_ago = datetime.now() - timedelta(minutes=int(os.getenv("AGENT_STATS_RECENT_MINUTES", "5")))
            very_recent_decisions = [
                d for d in self.decisions
                if d["timestamp"] > five_min_ago
            ]

            stats = {
                "last_hour": {
                    "total_decisions": len(recent_decisions),
                    "success_rate": (sum(1 for d in recent_decisions if d["success"]) / len(recent_decisions) * 100) if recent_decisions else 0,
                    "avg_execution_time_ms": (sum(d["execution_time_ms"] for d in recent_decisions) / len(recent_decisions)) if recent_decisions else 0
                },
                "last_5_minutes": {
                    "total_decisions": len(very_recent_decisions),
                    "success_rate": (sum(1 for d in very_recent_decisions if d["success"]) / len(very_recent_decisions) * 100) if very_recent_decisions else 0,
                    "avg_execution_time_ms": (sum(d["execution_time_ms"] for d in very_recent_decisions) / len(very_recent_decisions)) if very_recent_decisions else 0
                },
                "timestamp": datetime.now().isoformat()
            }

            return {
                "success": True,
                "stats": stats
            }

        except Exception as e:
            logger.error(
                "Failed to get realtime stats",
                error=str(e),
                exc_info=e
            )
            return {
                "success": False,
                "error": str(e)
            }


# 全局实例
agent_monitor_service = AgentMonitorService()
