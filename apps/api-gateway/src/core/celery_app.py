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
    },
)

# 自动发现任务
celery_app.autodiscover_tasks(["src.core"])

logger.info(
    "Celery应用初始化完成",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
