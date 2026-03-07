"""
Celery配置和应用实例
"""
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue
import os
import structlog

from .config import settings

logger = structlog.get_logger()

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
    timezone="Asia/Shanghai",
    enable_utc=True,

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
    task_default_retry_delay=int(os.getenv("CELERY_RETRY_DELAY", "60")),      # 默认重试延迟N秒
    task_max_retries=int(os.getenv("CELERY_MAX_RETRIES", "3")),               # 最大重试N次

    # Worker配置
    worker_prefetch_multiplier=int(os.getenv("CELERY_PREFETCH_MULTIPLIER", "4")),          # 每个worker预取N个任务
    worker_max_tasks_per_child=int(os.getenv("CELERY_MAX_TASKS_PER_CHILD", "1000")),       # 每个worker子进程最多执行N个任务后重启

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
        "src.core.celery_tasks.pull_historical_backfill": {
            "queue": "low_priority",
            "routing_key": "low_priority",
        },
        "src.core.celery_tasks.ops_patrol": {
            "queue": "high_priority",
            "routing_key": "high_priority",
        },
        "src.core.celery_tasks.dispatch_agent_message": {
            "queue": "high_priority",   # P0/P1 走高优先队列；fire_and_forget 本身按 priority 选队列
            "routing_key": "high_priority",
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
            "schedule": crontab(hour=int(os.getenv("CELERY_RAG_REPORT_HOUR", "6")), minute=int(os.getenv("CELERY_RAG_REPORT_MINUTE", "0"))),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 6,
            },
        },
        # 每天10AM检查库存预警(午高峰前)
        "check-inventory-alert": {
            "task": "src.core.celery_tasks.check_inventory_alert",
            "schedule": crontab(hour=int(os.getenv("CELERY_INVENTORY_CHECK_HOUR", "10")), minute=int(os.getenv("CELERY_INVENTORY_CHECK_MINUTE", "0"))),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 7,
            },
        },
        # 每日22:30生成当日营业日报
        "generate-daily-reports": {
            "task": "src.core.celery_tasks.generate_and_send_daily_report",
            "schedule": crontab(hour=int(os.getenv("CELERY_BUSINESS_REPORT_HOUR", "22")), minute=int(os.getenv("CELERY_BUSINESS_REPORT_MINUTE", "30"))),
            "args": (),  # 将为所有门店生成报告
            "options": {
                "queue": "default",
                "priority": 5,
            },
        },
        # 每日凌晨3点执行POS对账
        "perform-daily-reconciliation": {
            "task": "src.core.celery_tasks.perform_daily_reconciliation",
            "schedule": crontab(hour=int(os.getenv("CELERY_RECONCILIATION_HOUR", "3")), minute=int(os.getenv("CELERY_RECONCILIATION_MINUTE", "0"))),
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
        # 每日 17:00 启动晚间多阶段规划工作流（为所有门店规划 Day N+1）
        "start-evening-planning": {
            "task": "tasks.start_evening_planning_all_stores",
            "schedule": crontab(hour=17, minute=0),
            "args": (),
            "options": {
                "queue": "default",
                "priority": 9,   # 最高优先级，必须准时执行
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
            "schedule": crontab(minute=5),   # 每小时第 5 分钟执行，错开整点高峰
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
    },
)

# 自动发现任务
celery_app.autodiscover_tasks(["src.core"])

logger.info(
    "Celery应用初始化完成",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
