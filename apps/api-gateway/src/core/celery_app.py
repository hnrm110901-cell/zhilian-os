"""
Celery配置和应用实例
"""

import os
from typing import Optional, Tuple

import structlog
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue

from .config import settings

logger = structlog.get_logger()


def _env_int(
    keys: Tuple[str, ...],
    default: int,
    *,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    """从多个环境变量名中取第一个有效整数；非法值回退到默认值。"""
    for key in keys:
        raw = os.getenv(key)
        if raw is None:
            continue
        try:
            value = int(raw)
        except ValueError:
            logger.warning("invalid_env_int_fallback", key=key, raw=raw, default=default)
            return default
        if min_value is not None and value < min_value:
            logger.warning("env_int_below_min_fallback", key=key, raw=raw, default=default, min_value=min_value)
            return default
        if max_value is not None and value > max_value:
            logger.warning("env_int_above_max_fallback", key=key, raw=raw, default=default, max_value=max_value)
            return default
        return value
    return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


_celery_timezone = os.getenv("CELERY_TIMEZONE", "Asia/Shanghai")
_celery_enable_utc = _env_bool("CELERY_ENABLE_UTC", True)

# 07:00 人力任务：支持 L8_*（历史）和 CELERY_*（通用）两套变量名
_workforce_hour = _env_int(("L8_WORKFORCE_HOUR", "CELERY_WORKFORCE_HOUR"), 7, min_value=0, max_value=23)
_workforce_minute = _env_int(("L8_WORKFORCE_MINUTE", "CELERY_WORKFORCE_MINUTE"), 0, min_value=0, max_value=59)
_auto_schedule_hour = _env_int(("L8_AUTO_SCHEDULE_HOUR", "CELERY_AUTO_SCHEDULE_HOUR"), 7, min_value=0, max_value=23)
_auto_schedule_minute = _env_int(("L8_AUTO_SCHEDULE_MINUTE", "CELERY_AUTO_SCHEDULE_MINUTE"), 0, min_value=0, max_value=59)

# 创建Celery应用实例
celery_app = Celery(
    "zhilian_os",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery配置
celery_app.conf.update(
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=_celery_timezone,
    enable_utc=_celery_enable_utc,
    # 任务结果配置
    result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "3600")),  # 结果保留N秒
    result_backend_transport_options={
        "master_name": "mymaster",
        "retry_on_timeout": True,
    },
    # 任务执行配置
    task_acks_late=True,  # 任务完成后才确认
    task_reject_on_worker_lost=True,  # Worker丢失时拒绝任务
    task_track_started=True,  # 跟踪任务开始状态
    # 重试配置
    task_default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),  # 默认重试延迟N秒
    task_max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),  # 最大重试N次
    # Worker配置
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH_MULTIPLIER", "4")),  # 每个worker预取N个任务
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "1000")),  # 每个worker子进程最多执行N个任务后重启
    # 队列配置
    task_queues=(
        # 高优先级队列 - 实时事件处理
        Queue(
            "high_priority",
            Exchange("high_priority"),
            routing_key="high_priority",
            queue_arguments={"x-max-priority": 10},
        ),
        # 默认队列 - 普通事件处理
        Queue(
            "default",
            Exchange("default"),
            routing_key="default",
            queue_arguments={"x-max-priority": 5},
        ),
        # 低优先级队列 - 批量处理和ML训练
        Queue(
            "low_priority",
            Exchange("low_priority"),
            routing_key="low_priority",
            queue_arguments={"x-max-priority": 1},
        ),
    ),
    # 任务路由
    task_routes={
        "src.core.celery_tasks.process_neural_event": {
            "queue": "high_priority",
            "routing_key": "high_priority",
        },
        "src.core.celery_tasks.index_to_vector_db": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.train_federated_model": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "src.core.celery_tasks.generate_and_send_daily_report": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.perform_daily_reconciliation": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.detect_revenue_anomaly": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.generate_daily_report_with_rag": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.check_inventory_alert": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.generate_daily_hub": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.dispatch_training_recommendation": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.verify_training_effectiveness": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "src.core.celery_tasks.propagate_training_knowledge": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "tasks.release_expired_room_locks": {
            "queue": "default",
            "routing_key": "default",
        },
        "tasks.monthly_save_fct_tax": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.scan_lifecycle_transitions": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.dispatch_stale_journeys": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.generate_and_send_weekly_report": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.refresh_private_domain_rfm": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "src.core.celery_tasks.trigger_new_member_journeys": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.trigger_demand_predictions": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.trigger_birthday_reminders": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.pull_tiancai_daily_orders": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.pull_pinzhi_daily_data": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.pull_historical_backfill": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "src.core.celery_tasks.push_sm_daily_briefing": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.push_hq_daily_briefing": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.run_signal_bus_scan": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.ops_patrol": {
            "queue": "high_priority",
            "routing_key": "high_priority",
        },
        "src.core.celery_tasks.dispatch_agent_message": {
            "queue": "high_priority",  # P0/P1 走高优先队列；fire_and_forget 本身按 priority 选队列
            "routing_key": "high_priority",
        },
        "src.core.celery_tasks.member_agent_dormant_sweep": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.revenue_growth_monthly_report": {
            "queue": "default",
            "routing_key": "default",
        },
        "tasks.push_daily_workforce_advice": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.scheduled_im_roster_sync": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.retry_failed_dingtalk_messages": {
            "queue": "high_priority",
            "routing_key": "high_priority",
        },
        "src.core.celery_tasks.remind_incomplete_onboarding": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.sweep_milestone_notifications": {
            "queue": "default",
            "routing_key": "default",
        },
        "check_approval_timeouts": {
            "queue": "default",
            "routing_key": "default",
        },
        "src.core.celery_tasks.run_decision_effect_reviews": {
            "queue": "default",
            "routing_key": "default",
        },
    },
    # Celery Beat定时任务调度
    beat_schedule={
        # 每15分钟检测营收异常
        "detect-revenue-anomaly": {
            "task": "src.core.celery_tasks.detect_revenue_anomaly",
            "schedule": crontab(minute=f"*/{os.getenv('CELERY_ANOMALY_DETECT_INTERVAL', '15')}"),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 7,
            },
        },
        # 每天6AM生成昨日简报(RAG增强)
        "generate-daily-report-rag": {
            "task": "src.core.celery_tasks.generate_daily_report_with_rag",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_RAG_REPORT_HOUR", "6")), minute=int(os.getenv("CELERY_RAG_REPORT_MINUTE", "0"))
            ),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 6,
            },
        },
        # 每天10AM检查库存预警(午高峰前)
        "check-inventory-alert": {
            "task": "src.core.celery_tasks.check_inventory_alert",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_INVENTORY_CHECK_HOUR", "10")),
                minute=int(os.getenv("CELERY_INVENTORY_CHECK_MINUTE", "0")),
            ),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 7,
            },
        },
        # 每日22:30生成当日营业日报
        "generate-daily-reports": {
            "task": "src.core.celery_tasks.generate_and_send_daily_report",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_BUSINESS_REPORT_HOUR", "22")),
                minute=int(os.getenv("CELERY_BUSINESS_REPORT_MINUTE", "30")),
            ),
            "args": (),  # 将为所有门店生成报告
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # 每日凌晨3点执行POS对账
        "perform-daily-reconciliation": {
            "task": "src.core.celery_tasks.perform_daily_reconciliation",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_RECONCILIATION_HOUR", "3")),
                minute=int(os.getenv("CELERY_RECONCILIATION_MINUTE", "0")),
            ),
            "args": (),  # 将为所有门店执行对账
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # 每日22:30生成 T+1 备战板
        "generate-daily-hub": {
            "task": "src.core.celery_tasks.generate_daily_hub",
            "schedule": crontab(hour=22, minute=30),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 6,
            },
        },
        # 每10分钟执行 L4 Action 超时升级（P0 30min / P1 2h 等）
        "escalate-ontology-actions": {
            "task": "src.core.celery_tasks.escalate_ontology_actions",
            "schedule": crontab(minute=f"*/{os.getenv('CELERY_ESCALATION_INTERVAL', '10')}"),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 7,
            },
        },
        # Phase 3.2: 每周一 3AM 跨门店培训知识传播
        "propagate-training-knowledge": {
            "task": "src.core.celery_tasks.propagate_training_knowledge",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_CROSS_STORE_TRAINING_HOUR", "3")),
                minute=0,
                day_of_week=1,  # 周一
            ),
            "args": (),
            "options": {
                "queue": "low_priority",
                "priority": 2,
            },
        },
        # 每日凌晨 2AM 同步 PG 主数据 → Neo4j 图谱
        "sync-ontology-graph": {
            "task": "src.core.celery_tasks.sync_ontology_graph",
            "schedule": crontab(
                hour=int(os.getenv("CELERY_ONTOLOGY_SYNC_HOUR", "2")),
                minute=0,
            ),
            "args": (),
            "options": {
                "queue": "low_priority",
                "priority": 3,
            },
        },
        # ARCH-003: 每日凌晨 2AM 更新门店记忆层
        "update-store-memory": {
            "task": "src.core.celery_tasks.update_store_memory",
            "schedule": crontab(hour=2, minute=0),
            "args": (),
            "options": {
                "queue": "low_priority",
                "priority": 3,
            },
        },
        # FEAT-002: 每日9AM 推送预测性备料建议
        "push-daily-forecast": {
            "task": "src.core.celery_tasks.push_daily_forecast",
            "schedule": crontab(hour=9, minute=0),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # L8: 每日 07:00 推送今日人力建议（可通过环境变量覆盖）
        "daily-workforce-advice": {
            "task": "tasks.push_daily_workforce_advice",
            "schedule": crontab(
                hour=_workforce_hour,
                minute=_workforce_minute,
            ),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 9,
            },
        },
        # L8: 每日 07:00 自动排班（预算硬约束 + 异常提醒）
        "daily-auto-workforce-schedule": {
            "task": "tasks.auto_generate_workforce_schedule",
            "schedule": crontab(
                hour=_auto_schedule_hour,
                minute=_auto_schedule_minute,
            ),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 9,
            },
        },
        # 每日 17:00 启动晚间多阶段规划工作流（为所有门店规划 Day N+1）
        "start-evening-planning": {
            "task": "tasks.start_evening_planning_all_stores",
            "schedule": crontab(hour=17, minute=0),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 9,  # 最高优先级，必须准时执行
            },
        },
        # 每 5 分钟检查工作流 deadline（T-10min 预警 + 过期自动锁定）
        "check-workflow-deadlines": {
            "task": "tasks.check_workflow_deadlines",
            "schedule": crontab(minute="*/5"),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 8,
            },
        },
        # 每日凌晨1点释放超时锁台（room_lock 超过 ROOM_LOCK_TIMEOUT_DAYS 未签约则回退到 intent）
        "release-expired-room-locks": {
            "task": "tasks.release_expired_room_locks",
            "schedule": crontab(hour=1, minute=0),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # INFRA-002: 每5分钟重试失败的企微消息
        "retry-failed-wechat-messages": {
            "task": "src.core.celery_tasks.retry_failed_wechat_messages",
            "schedule": crontab(minute="*/5"),
            "args": (),
            "options": {
                "queue": "high_priority",
                "priority": 8,
            },
        },
        # 每月1日凌晨1:00 自动保存上月税务记录（FCT 业财税一体化）
        "monthly-save-fct-tax": {
            "task": "tasks.monthly_save_fct_tax",
            "schedule": crontab(hour=1, minute=0, day_of_month=1),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # ── v2.0 决策型企微推送（4时间点）────────────────────────────────────────
        # 08:00晨推：今日 Top3 决策卡片
        "push-morning-decisions": {
            "task": "src.core.celery_tasks.push_morning_decisions",
            "schedule": crontab(
                hour=int(os.getenv("PUSH_MORNING_HOUR", "8")),
                minute=int(os.getenv("PUSH_MORNING_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # 12:00午推：上午异常汇总（损耗/成本率）
        "push-noon-anomaly": {
            "task": "src.core.celery_tasks.push_noon_anomaly",
            "schedule": crontab(
                hour=int(os.getenv("PUSH_NOON_HOUR", "12")),
                minute=int(os.getenv("PUSH_NOON_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # 17:30战前推：库存/排班备战核查
        "push-prebattle": {
            "task": "src.core.celery_tasks.push_prebattle_decisions",
            "schedule": crontab(
                hour=int(os.getenv("PUSH_PREBATTLE_HOUR", "17")),
                minute=int(os.getenv("PUSH_PREBATTLE_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 9},
        },
        # 20:30晚推：当日回顾+待批决策提醒
        "push-evening-recap": {
            "task": "src.core.celery_tasks.push_evening_recap",
            "schedule": crontab(
                hour=int(os.getenv("PUSH_EVENING_HOUR", "20")),
                minute=int(os.getenv("PUSH_EVENING_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # 09:30 食材成本率 KPI 阈值检查（AlertThresholdsPage 配置驱动）
        "check-food-cost-kpi-alert": {
            "task": "src.core.celery_tasks.check_food_cost_kpi_alert",
            "schedule": crontab(
                hour=int(os.getenv("FOOD_COST_ALERT_HOUR", "9")),
                minute=int(os.getenv("FOOD_COST_ALERT_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # 09:45 成本率趋势预测告警（提前识别恶化趋势，在超标前预警）
        "check-food-cost-trend-alert": {
            "task": "src.core.celery_tasks.check_food_cost_trend_alert",
            "schedule": crontab(
                hour=int(os.getenv("FOOD_COST_TREND_ALERT_HOUR", "9")),
                minute=int(os.getenv("FOOD_COST_TREND_ALERT_MINUTE", "45")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # 10:30 营销自动触达：批量企微挽回流失风险客户（FrequencyCapEngine 频控保护）
        "marketing-auto-outreach": {
            "task": "src.core.celery_tasks.marketing_auto_outreach",
            "schedule": crontab(
                hour=int(os.getenv("MARKETING_OUTREACH_HOUR", "10")),
                minute=int(os.getenv("MARKETING_OUTREACH_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # 06:00 私域生命周期扫描（churn_warning / inactivity_long → 自动触发旅程）
        "scan-lifecycle-transitions": {
            "task": "src.core.celery_tasks.scan_lifecycle_transitions",
            "schedule": crontab(
                hour=int(os.getenv("LIFECYCLE_SCAN_HOUR", "6")),
                minute=int(os.getenv("LIFECYCLE_SCAN_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # 每日凌晨 3:30 刷新私域会员 RFM 指标（3:00 对账完成后执行）
        "refresh-private-domain-rfm": {
            "task": "src.core.celery_tasks.refresh_private_domain_rfm",
            "schedule": crontab(hour=3, minute=30),
            "args": (),
            "options": {"queue": "low_priority", "priority": 3},
        },
        # 每小时触发新会员激活旅程
        "trigger-new-member-journeys": {
            "task": "src.core.celery_tasks.trigger_new_member_journeys",
            "schedule": crontab(minute=5),  # 每小时第 5 分钟执行，错开整点高峰
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # Agent-13: 每日 09:15 主动触达即将到店的高频会员
        "trigger-demand-predictions": {
            "task": "src.core.celery_tasks.trigger_demand_predictions",
            "schedule": crontab(hour=9, minute=15),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # EventScheduler: 每日 10:00 触发生日/入会周年祝福
        "trigger-birthday-reminders": {
            "task": "src.core.celery_tasks.trigger_birthday_reminders",
            "schedule": crontab(hour=10, minute=0),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # 每日凌晨 01:30 拉取品智 POS 昨日数据（订单+汇总）
        "pull-pinzhi-daily-data": {
            "task": "src.core.celery_tasks.pull_pinzhi_daily_data",
            "schedule": crontab(
                hour=int(os.getenv("PINZHI_PULL_HOUR", "1")),
                minute=int(os.getenv("PINZHI_PULL_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # 每日凌晨 02:00 拉取天财商龙昨日订单（在 03:00 POS 对账前完成入库）
        "pull-tiancai-daily-orders": {
            "task": "src.core.celery_tasks.pull_tiancai_daily_orders",
            "schedule": crontab(
                hour=int(os.getenv("TIANCAI_PULL_HOUR", "2")),
                minute=int(os.getenv("TIANCAI_PULL_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # 每日凌晨 02:15 拉取奥琦玮供应链数据（采购入库单 + 库存快照）
        "pull-aoqiwei-daily-supply": {
            "task": "src.core.celery_tasks.pull_aoqiwei_daily_supply",
            "schedule": crontab(
                hour=int(os.getenv("AOQIWEI_PULL_HOUR", "2")),
                minute=int(os.getenv("AOQIWEI_PULL_MINUTE", "15")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # 每日凌晨 02:25 奥琦玮CRM会员数据增强（基于近30天订单手机号逐条查询）
        "enrich-members-aoqiwei-crm": {
            "task": "src.core.celery_tasks.enrich_members_from_aoqiwei_crm",
            "schedule": crontab(
                hour=int(os.getenv("AOQIWEI_CRM_ENRICH_HOUR", "2")),
                minute=int(os.getenv("AOQIWEI_CRM_ENRICH_MINUTE", "25")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # Sprint 1 CDP: POS拉取后回填 consumer_id（02:30 紧跟 POS 拉取）
        "cdp-sync-consumer-ids": {
            "task": "src.core.celery_tasks.cdp_sync_consumer_ids",
            "schedule": crontab(
                hour=int(os.getenv("CDP_SYNC_HOUR", "2")),
                minute=int(os.getenv("CDP_SYNC_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # Sprint 2 CDP: consumer_id 驱动的 RFM 重算（03:00，旧 RFM 刷新在 03:30）
        "cdp-rfm-recalculate": {
            "task": "src.core.celery_tasks.cdp_rfm_recalculate",
            "schedule": crontab(
                hour=int(os.getenv("CDP_RFM_HOUR", "3")),
                minute=int(os.getenv("CDP_RFM_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # Sprint 4: 每月1日 08:00 生成上月增收月报
        "revenue-growth-monthly-report": {
            "task": "src.core.celery_tasks.revenue_growth_monthly_report",
            "schedule": crontab(
                hour=int(os.getenv("REVENUE_REPORT_HOUR", "8")),
                minute=int(os.getenv("REVENUE_REPORT_MINUTE", "0")),
                day_of_month=1,
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # Sprint 3 MemberAgent: 每日 06:30 自动扫描沉睡会员并触发唤醒旅程（KPI: ≥50条/周）
        "member-agent-dormant-sweep": {
            "task": "src.core.celery_tasks.member_agent_dormant_sweep",
            "schedule": crontab(
                hour=int(os.getenv("MEMBER_AGENT_SWEEP_HOUR", "6")),
                minute=int(os.getenv("MEMBER_AGENT_SWEEP_MINUTE", "30")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # P3: 每N分钟 OpsAgent 巡检 + P0 级别自动推送企微告警
        "ops-patrol": {
            "task": "src.core.celery_tasks.ops_patrol",
            "schedule": crontab(minute=f"*/{os.getenv('OPS_PATROL_INTERVAL', '15')}"),
            "args": (),
            "options": {
                "queue": "high_priority",
                "priority": 9,
            },
        },
        # Phase 7 — L5 夜间行动批量派发（在 L4 nightly_reasoning_scan 04:00 完成后执行）
        "nightly-action-dispatch": {
            "task": "tasks.nightly_action_dispatch",
            "schedule": crontab(
                hour=int(os.getenv("L5_DISPATCH_HOUR", "4")),
                minute=int(os.getenv("L5_DISPATCH_MINUTE", "30")),
            ),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 8,
            },
        },
        # P2 — 店长版每日简报（08:00 推送）
        "push-sm-daily-briefing": {
            "task": "src.core.celery_tasks.push_sm_daily_briefing",
            "schedule": crontab(
                hour=int(os.getenv("SM_BRIEFING_HOUR", "8")),
                minute=int(os.getenv("SM_BRIEFING_MINUTE", "5")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 9},
        },
        # P3 — 老板多店版简报（08:10 推送，晚于店长版）
        "push-hq-daily-briefing": {
            "task": "src.core.celery_tasks.push_hq_daily_briefing",
            "schedule": crontab(
                hour=int(os.getenv("HQ_BRIEFING_HOUR", "8")),
                minute=int(os.getenv("HQ_BRIEFING_MINUTE", "10")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 8},
        },
        # SignalBus — 每2小时扫描（差评/临期库存/大桌预订 → 自动路由）
        "signal-bus-scan": {
            "task": "src.core.celery_tasks.run_signal_bus_scan",
            "schedule": crontab(minute=0, hour="*/2"),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # P2 — 每日03:30 决策效果闭环评估（扫描已执行未评估的 DecisionLog）
        "evaluate-decision-effects": {
            "task": "src.core.celery_tasks.evaluate_decision_effects",
            "schedule": crontab(hour=3, minute=30),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # IM 通讯录定时同步（每日 02:00，在 POS 对账前完成人员同步）
        "scheduled-im-roster-sync": {
            "task": "src.core.celery_tasks.scheduled_im_roster_sync",
            "schedule": crontab(
                hour=int(os.getenv("IM_SYNC_HOUR", "2")),
                minute=int(os.getenv("IM_SYNC_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # IM 考勤数据同步（每日 06:00，同步昨日打卡数据）
        "scheduled-im-attendance-sync": {
            "task": "src.core.celery_tasks.scheduled_im_attendance_sync",
            "schedule": crontab(
                hour=int(os.getenv("IM_ATTENDANCE_SYNC_HOUR", "6")),
                minute=int(os.getenv("IM_ATTENDANCE_SYNC_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # 每5分钟重试失败的钉钉消息
        "retry-failed-dingtalk-messages": {
            "task": "src.core.celery_tasks.retry_failed_dingtalk_messages",
            "schedule": crontab(minute="*/5"),
            "args": (),
            "options": {"queue": "high_priority", "priority": 8},
        },
        # Phase 4: 每日 09:00 提醒入职任务未完成的新员工
        "remind-incomplete-onboarding": {
            "task": "src.core.celery_tasks.remind_incomplete_onboarding",
            "schedule": crontab(
                hour=int(os.getenv("ONBOARDING_REMIND_HOUR", "9")),
                minute=int(os.getenv("ONBOARDING_REMIND_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # Phase 4: 每日 10:00 扫描未推送的里程碑/技能认证通知
        "sweep-milestone-notifications": {
            "task": "src.core.celery_tasks.sweep_milestone_notifications",
            "schedule": crontab(
                hour=int(os.getenv("MILESTONE_SWEEP_HOUR", "10")),
                minute=int(os.getenv("MILESTONE_SWEEP_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # Phase 3 HR: 每日 08:00 合规告警扫描（健康证/合同/身份证到期）
        "check-compliance-alerts-daily": {
            "task": "check_compliance_alerts",
            "schedule": crontab(hour=8, minute=0),  # 每日 08:00
            "options": {"queue": "default"},
        },
        # W2-1: 每小时整点检查超期审批（自动升级/催办）
        "check-approval-timeouts-hourly": {
            "task": "check_approval_timeouts",
            "schedule": crontab(minute=0),  # 每小时整点
            "args": (),
            "options": {"queue": "default", "priority": 6},
        },
        # Phase 2 飞轮: 每日 04:00 扫描已执行决策的30/60/90天效果回顾
        "decision-flywheel-effect-review": {
            "task": "src.core.celery_tasks.run_decision_effect_reviews",
            "schedule": crontab(
                hour=int(os.getenv("FLYWHEEL_REVIEW_HOUR", "4")),
                minute=int(os.getenv("FLYWHEEL_REVIEW_MINUTE", "0")),
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
        # Phase 9 — 每3分钟检测边缘主机心跳，离线自动创建 P1 告警
        "check-edge-hub-heartbeats": {
            "task": "tasks.check_edge_hub_heartbeats",
            "schedule": crontab(minute=f"*/{os.getenv('EDGE_HUB_HEARTBEAT_CHECK_INTERVAL', '3')}"),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 8,
            },
        },
        # 私域旅程 catch-up：每5分钟扫描 next_action_at 过期的 running 旅程并重新调度
        "dispatch-stale-journeys": {
            "task": "src.core.celery_tasks.dispatch_stale_journeys",
            "schedule": crontab(minute="*/5"),
            "args": (),
            "options": {"queue": "default", "priority": 7},
        },
        # 周报：每周五 10:00 UTC（北京 18:00）生成本周汇总 + 企微推送
        "generate-weekly-report": {
            "task": "src.core.celery_tasks.generate_and_send_weekly_report",
            "schedule": crontab(
                hour=int(os.getenv("WEEKLY_REPORT_HOUR", "10")),
                minute=int(os.getenv("WEEKLY_REPORT_MINUTE", "0")),
                day_of_week=int(os.getenv("WEEKLY_REPORT_DOW", "5")),  # 5=Friday
            ),
            "args": (),
            "options": {"queue": "default", "priority": 5},
        },
    },
)

# 自动发现任务
celery_app.autodiscover_tasks(["src.core"])

logger.info(
    "Celery应用初始化完成",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    timezone=_celery_timezone,
    enable_utc=_celery_enable_utc,
    workforce_schedule=f"{_workforce_hour:02d}:{_workforce_minute:02d}",
    auto_schedule=f"{_auto_schedule_hour:02d}:{_auto_schedule_minute:02d}",
)
